import json
import os

from moviepy import AudioFileClip, concatenate_videoclips
from moviepy.video.fx.FadeIn import FadeIn
from moviepy.video.fx.FadeOut import FadeOut

from app.services.kenburns import build_kenburns_clip


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


def build_video(project_path: str):

    scenes = _load_scenes(project_path)

    if not scenes:
        raise Exception("Scene이 없습니다.")

    scene_audio_folder = os.path.join(
        project_path,
        "audio",
        "scenes",
    )

    clips = []

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

        fade = _fade_duration(duration)

        clip = clip.with_effects(
            [
                FadeIn(fade),
                FadeOut(fade),
            ]
        )

        clips.append(
            clip
        )

    final = concatenate_videoclips(
        clips,
        method="compose",
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