import json
import os

from moviepy import AudioFileClip, concatenate_videoclips
from moviepy.video.fx.CrossFadeIn import CrossFadeIn
from moviepy.video.fx.CrossFadeOut import CrossFadeOut
from moviepy.video.fx.FadeIn import FadeIn
from moviepy.video.fx.FadeOut import FadeOut

from app.services.kenburns import build_kenburns_clip
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

# Sprint55 - Adaptive Scene Timing. 각 scene의 Ken Burns clip 길이는
# 이미 Sprint37-1부터 그 scene의 실제 narration(mp3) 길이를 그대로
# 쓴다 - "narration 길이에 맞춘 자동 duration"은 이미 존재한다. 여기서
# 추가하는 건 그 위에 씌우는 최소/최대 안전장치뿐이다: 너무 짧은
# scene(예: 한 문장짜리)은 Ken Burns 모션이 부자연스럽게 빨라지고,
# 너무 긴 scene(예: Duration Optimizer가 무음을 patch 붙인 마지막
# scene)은 화면이 늘어져 보인다.
MIN_SCENE_DURATION = 2.0
MAX_SCENE_DURATION = 14.0


def _apply_duration_limits(
    raw_durations: list,
    min_duration: float = MIN_SCENE_DURATION,
    max_duration: float = MAX_SCENE_DURATION,
) -> list:
    """
    각 scene의 실제 narration 길이(raw_durations)를 [min_duration,
    max_duration] 범위로 눌러 담되, 전체 합(=narration 총 길이)은
    정확히 보존한다. 범위를 벗어난 scene을 경계값으로 고정하고, 그
    차이를 아직 고정되지 않은 나머지 scene들에 비율대로 나눠 분배하는
    것을 반복한다(water-filling). 총합 자체가 [n*min, n*max] 범위
    밖이라 두 조건을 동시에 만족할 수 없으면, 범위 제한보다 합 보존을
    우선한다 - "scene duration 합은 narration 길이와 동일"이 하드
    요구사항이기 때문이다.

    순수 함수입니다 - 입력 리스트를 변경하지 않습니다.
    """

    n = len(raw_durations)

    if n == 0:
        return []

    total = sum(raw_durations)

    if total < min_duration * n or total > max_duration * n:
        # 두 제약을 동시에 만족하는 것 자체가 불가능 - 합 보존을 우선하고
        # 그대로 반환한다.
        return list(raw_durations)

    adjusted = list(raw_durations)
    locked = [False] * n

    for _ in range(n):

        for i in range(n):
            if locked[i]:
                continue
            if adjusted[i] < min_duration:
                adjusted[i] = min_duration
                locked[i] = True
            elif adjusted[i] > max_duration:
                adjusted[i] = max_duration
                locked[i] = True

        deficit = total - sum(adjusted)

        if abs(deficit) < 1e-9:
            break

        free_indices = [i for i in range(n) if not locked[i]]

        if not free_indices:
            adjusted[-1] += deficit
            break

        free_total = sum(adjusted[i] for i in free_indices)

        for i in free_indices:
            share = (
                adjusted[i] / free_total
                if free_total > 0
                else 1 / len(free_indices)
            )
            adjusted[i] += deficit * share

    return adjusted


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
    Sprint62-2 - scene["assets"](Sprint62-1)가 있고 비어있지 않으면
    첫 번째 asset의 path를 사용합니다. 아직 asset 하나만 순회 없이
    읽습니다(Visual Diversity 기반 구조 준비 단계). assets가 없으면
    기존 asset_path(step02_assets.py 경로)를 그대로 사용하고, 그마저도
    없으면 기존 step02_image.py 파이프라인과의 하위호환을 위해 기존
    파일명 규칙(images/sceneN.png)으로 폴백합니다.
    """

    assets = scene.get("assets")

    if assets:
        return assets[0]["path"]

    asset_path = scene.get("asset_path")

    if asset_path:
        return asset_path

    return os.path.join(
        project_path,
        "images",
        f"scene{scene['scene']}.png",
    )


def _resolve_asset_paths(project_path, scene):
    """
    Sprint62-3 - scene["assets"]의 모든 항목을 순서대로 담은 경로
    목록을 반환합니다(Scene을 여러 컷으로 순차 재생하기 위함). assets가
    없거나 비어있으면 기존 _resolve_asset_path()의 단일 결과를 그대로
    1개짜리 리스트로 반환해 완전히 하위 호환됩니다.
    """

    assets = scene.get("assets")

    if assets:
        return [asset["path"] for asset in assets]

    return [_resolve_asset_path(project_path, scene)]


def _split_duration_equally(total_duration, count):
    """
    Sprint62-3 - Scene duration을 asset 개수로 균등 분배합니다. 합은
    항상 total_duration과 정확히 일치합니다.
    """

    if count <= 1:
        return [total_duration]

    per_cut = total_duration / count

    return [per_cut] * count


def _build_scene_clip(asset_paths, clip_duration):
    """
    Sprint62-3 - Scene 하나를 구성하는 clip을 만듭니다. asset이 1개면
    기존과 완전히 동일하게 단일 Ken Burns clip을 반환합니다(렌더링
    경로 무변경). 여러 개면 clip_duration을 균등 분배해 asset마다
    Ken Burns clip을 만들고 순서대로 이어 붙입니다 - 컷 사이에는 별도
    효과를 적용하지 않습니다(scene 경계의 crossfade/fade는 기존처럼
    이 clip 전체의 앞/뒤에만 적용됩니다).
    """

    if len(asset_paths) == 1:
        return build_kenburns_clip(asset_paths[0], clip_duration).with_fps(30)

    cut_durations = _split_duration_equally(clip_duration, len(asset_paths))

    cuts = [
        build_kenburns_clip(path, duration).with_fps(30)
        for path, duration in zip(asset_paths, cut_durations)
    ]

    return concatenate_videoclips(cuts, method="compose").with_fps(30)


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

    scenes = annotate_scenes_with_transitions(_load_scenes(project_path))

    if not scenes:
        raise Exception("Scene이 없습니다.")

    scene_audio_folder = os.path.join(
        project_path,
        "audio",
        "scenes",
    )

    scene_asset_paths = []
    durations = []

    for scene in scenes:

        asset_paths_for_scene = _resolve_asset_paths(project_path, scene)

        for asset_path in asset_paths_for_scene:
            if not os.path.exists(asset_path):
                raise Exception(
                    f"Scene {scene['scene']}의 asset 파일이 없습니다: {asset_path}"
                )

        scene_audio = os.path.join(
            scene_audio_folder,
            f"scene{scene['scene']}.mp3",
        )

        if not os.path.exists(scene_audio):
            raise Exception(
                f"Scene {scene['scene']}의 오디오 파일이 없습니다: {scene_audio}"
            )

        audio = AudioFileClip(scene_audio)

        durations.append(audio.duration)

        audio.close()

        scene_asset_paths.append(asset_paths_for_scene)

    durations = _apply_duration_limits(durations)

    last_index = len(scene_asset_paths) - 1
    overlap = CROSSFADE_DURATION

    raw_clips = []

    for index, asset_paths_for_scene in enumerate(scene_asset_paths):

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

        clip = _build_scene_clip(asset_paths_for_scene, clip_duration)

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
        preset="slow",
        audio=False,
        threads=4,
        logger="bar",
    )

    final.close()

    return output_path