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
    """

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

    scenes = annotate_scenes_with_transitions(_load_scenes(project_path))

    if not scenes:
        raise Exception("Scene이 없습니다.")

    scene_audio_folder = os.path.join(
        project_path,
        "audio",
        "scenes",
    )

    raw_clips = []
    durations = []

    for scene in scenes:

        asset_path = _resolve_asset_path(project_path, scene)

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

        duration = audio.duration

        audio.close()

        clip = build_kenburns_clip(
            asset_path,
            duration,
        )

        clip = clip.with_fps(30)

        raw_clips.append(clip)
        durations.append(duration)

    # 인접 clip끼리 겹쳐야(overlap) 실제 cross-dissolve가 되는데,
    # concatenate_videoclips의 padding은 clip 쌍마다가 아니라 전체
    # concatenation에 적용되는 단일 값이라, 어떤 scene의 안전 fade
    # 한도도 넘지 않도록 가장 작은 값을 공통 overlap으로 사용한다.
    overlap = min(_fade_duration(d) for d in durations)

    last_index = len(raw_clips) - 1

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