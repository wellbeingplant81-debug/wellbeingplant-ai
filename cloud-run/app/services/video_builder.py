import json
import os

from moviepy import concatenate_videoclips
from moviepy.video.fx.CrossFadeIn import CrossFadeIn
from moviepy.video.fx.CrossFadeOut import CrossFadeOut
from moviepy.video.fx.FadeIn import FadeIn
from moviepy.video.fx.FadeOut import FadeOut

from app.services.footage import build_footage_clip, is_footage
from app.services.kenburns import build_kenburns_clip
from app.services import scene_order
from app.services.scene_timeline import build_timeline
from app.services.transition_engine import annotate_scenes_with_transitions


MAX_FADE_DURATION = 0.35
FADE_DURATION_RATIO = 0.15
MIN_FADE_DURATION = 0.08

# Cross-dissolve 겹침 길이(초). Scene Timeline의 기준은 항상 audio
# duration이다 - concatenate_videoclips가 겹치는 만큼(padding) 영상
# 전체 길이를 줄이므로, 마지막 scene을 제외한 모든 clip의 재생 길이에
# 이 값을 그대로 더해 정확히 상쇄한다(Sprint37-1). 세 곳(clip 길이
# 연장 / CrossFadeIn·CrossFadeOut 길이 / concatenate_videoclips의
# padding)이 항상 동일한 이 상수 하나만 참조해야 한다 - 그래야 최종
# 영상 길이가 audio_service.py/subtitle_service.py가 이미 쓰고 있는
# 겹침 없는 누적 scene 타임라인과 정확히 일치한다.
CROSSFADE_DURATION = 0.35

# Sprint62 - Master Quality Render Pipeline.
#
# 여기서 만드는 short.mp4는 최종 산출물이 아니라, final_video_service.py가
# 자막을 번인하면서 곧바로 다시 인코딩해 final_short.mp4를 만드는 중간
# 산출물이다. 그런데 moviepy는 write_videofile에 -crf를 전혀 넘기지
# 않으므로(moviepy/video/io/ffmpeg_writer.py의 명령어 조립 참고), 우리가
# 아무것도 지정하지 않으면 libx264 기본값인 CRF 23으로 인코딩된다.
#
# 실측(2026-08-05, output/20260709_* 3건): 중간본이 1080x1920 30fps에서
# 1.04~1.82 Mbps에 불과했다. 2차 인코딩이 CRF 18이어도 1차에서 이미
# 버려진 디테일은 되살아나지 않는다 - Ken Burns처럼 화면 전체가 계속
# 움직이는 영상에서는 이 손실이 그대로 최종 화질 상한이 된다.
#
# 중간본은 다음 단계에서 즉시 재인코딩되고 버려지므로 압축 효율(파일
# 크기)은 아무 의미가 없다. 의미가 있는 것은 충실도와 렌더 속도뿐이다.
# 그래서 CRF는 시각적 무손실 영역까지 낮추고(품질 목표), preset은 오히려
# 빠른 쪽으로 올린다(같은 CRF를 더 빨리 도달하되 파일만 커짐). preset은
# 도달 방식일 뿐 품질 목표가 아니므로, 이 조합은 기존 CRF 23 + slow보다
# 항상 화질이 높다.
INTERMEDIATE_CRF = 16
INTERMEDIATE_PRESET = "veryfast"


def _intermediate_ffmpeg_params(crf: int = INTERMEDIATE_CRF) -> list:
    """
    중간본(short.mp4) 인코딩에 쓸 추가 ffmpeg 인자를 만든다. 순수
    함수입니다.

    -b:v(비트레이트 목표)는 절대 함께 주지 않는다 - libx264는 둘이
    동시에 주어지면 비트레이트를 우선해 CRF를 무시하기 때문이다.
    """

    return ["-crf", str(crf)]


def _fade_duration(duration):
    return max(
        MIN_FADE_DURATION,
        min(MAX_FADE_DURATION, duration * FADE_DURATION_RATIO),
    )


def _load_scenes(project_path):

    script_path = os.path.join(
        project_path,
        "script.json",
    )

    with open(
        script_path,
        "r",
        encoding="utf-8",
    ) as f:

        data = json.load(f)

    return sorted(
        data["scenes"],
        key=lambda scene: scene["scene"],
    )


def _resolve_asset_path(project_path, scene):
    """
    scene에 asset_path가 있으면(step02_assets.py 경로) 그대로 사용하고,
    없으면 기존 step02_image.py 파이프라인과의 하위호환을 위해 기존
    파일명 규칙(images/sceneN.png)으로 폴백합니다.

    Sprint223 - 받아 둔 스톡 영상이 있으면 그 영상이 이 scene의 자산이다.

    **파일이 실제로 있을 때만** 쓴다. 적혀만 있고 없으면 예전처럼
    그림으로 간다 - 첫 프레임은 영상과 함께 언제나 남으므로
    (asset_integration_service) 그 길이 늘 살아 있고, 사람이 videos/를
    지웠다는 이유로 렌더가 통째로 멈추지 않는다.
    """

    footage_path = scene.get("footage_path")

    if footage_path and os.path.exists(footage_path):
        return footage_path

    asset_path = scene.get("asset_path")

    if asset_path:
        return asset_path

    return os.path.join(
        project_path,
        "images",
        f"scene{scene['scene']}.png",
    )


def _effects_for_clip(index, last_index, scene, duration, overlap):
    """
    scene["transition"](transition_engine.py)에 따라 clip 하나에 적용할
    moviepy 효과 리스트를 결정합니다. 순수 함수입니다 (실제 렌더링/
    파일 접근 없음).

    "fade"인 경우에만 블랙에서 시작하는 강한 fade-in을 쓰고, 나머지는
    이전 clip과 겹쳐 보이는 실제 cross-dissolve(CrossFadeIn)를
    적용합니다. 마지막 clip은 항상 블랙으로 fade-out하고, 그 외에는
    다음 clip과 겹치는 cross-dissolve(CrossFadeOut)를 적용합니다.
    """

    effects = []

    if scene.get("transition") == "fade":
        effects.append(FadeIn(_fade_duration(duration)))
    else:
        effects.append(CrossFadeIn(overlap))

    if index == last_index:
        effects.append(FadeOut(_fade_duration(duration)))
    else:
        effects.append(CrossFadeOut(overlap))

    return effects


def build_video(project_path: str):

    # Sprint145 - 사람이 정한 차례가 있으면 그대로 따른다. 없으면
    # script.json에 적힌 그대로다(예전과 같다).
    scenes = annotate_scenes_with_transitions(
        scene_order.for_render(project_path, _load_scenes(project_path)),
    )

    if not scenes:
        raise Exception("Scene이 없습니다.")

    asset_paths = []

    for scene in scenes:

        asset_path = _resolve_asset_path(project_path, scene)

        if not os.path.exists(asset_path):
            raise Exception(
                f"Scene {scene['scene']}의 asset 파일이 없습니다: {asset_path}"
            )

        asset_paths.append(asset_path)

    # Sprint64 - Scene Timeline 단일화. 여기서 scene 길이를 직접 재지
    # 않는다. subtitle_service.py와 똑같은 타임라인(scene_timeline.py)을
    # 받아 쓰는 것이 요점이다 - 예전에는 이쪽이 moviepy 추정치에
    # duration clamp까지 얹어서 자막/오디오와 경계가 어긋났다.
    timeline = build_timeline(project_path, scenes)

    durations = [slot["duration"] for slot in timeline]

    last_index = len(asset_paths) - 1
    overlap = CROSSFADE_DURATION

    raw_clips = []

    for index, asset_path in enumerate(asset_paths):

        # 마지막 scene을 제외한 모든 clip은 다음 clip과 겹치는(overlap)
        # cross-dissolve 구간만큼 Ken Burns 재생 길이를 늘린다 - 이래야
        # concatenate_videoclips가 padding=-overlap으로 줄이는 길이가
        # 정확히 상쇄되어, 최종 영상 길이가 audio duration(scene
        # timeline의 기준)과 일치한다.
        clip_duration = (
            durations[index]
            if index == last_index
            else durations[index] + overlap
        )

        # Sprint223 - 사진이냐 영상이냐로 갈리는 유일한 자리다. 두
        # 함수가 돌려주는 것의 모양이 같으므로(1080x1920 · 그 길이 ·
        # 소리 없음) 아래 겹침 계산은 종류를 몰라도 된다 - 그 계산은
        # 이번에 한 줄도 바뀌지 않았다.
        clip = (
            build_footage_clip(asset_path, clip_duration,
                               scene_number=scenes[index]["scene"])
            if is_footage(asset_path)
            else build_kenburns_clip(asset_path, clip_duration)
        )

        clip = clip.with_fps(30)

        raw_clips.append(clip)

    clips = []

    for index, (clip, scene) in enumerate(zip(raw_clips, scenes)):

        effects = _effects_for_clip(
            index, last_index, scene, durations[index], overlap,
        )

        clips.append(clip.with_effects(effects))

    final = concatenate_videoclips(
        clips,
        method="compose",
        padding=-overlap,
    )

    video_folder = os.path.join(
        project_path,
        "video",
    )

    os.makedirs(
        video_folder,
        exist_ok=True,
    )

    output_path = os.path.join(
        video_folder,
        "short.mp4",
    )

    final.write_videofile(
        output_path,
        codec="libx264",
        fps=30,
        preset=INTERMEDIATE_PRESET,
        ffmpeg_params=_intermediate_ffmpeg_params(),
        audio=False,
        threads=4,
        logger="bar",
    )

    final.close()

    return output_path