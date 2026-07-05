import glob
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


def build_video(project_path: str):

    image_folder = os.path.join(
        project_path,
        "images",
    )

    scene_audio_folder = os.path.join(
        project_path,
        "audio",
        "scenes",
    )

    images = sorted(
        glob.glob(
            os.path.join(
                image_folder,
                "*.png",
            )
        )
    )

    scene_audios = sorted(
        glob.glob(
            os.path.join(
                scene_audio_folder,
                "*.mp3",
            )
        )
    )

    if not images:
        raise Exception("이미지가 없습니다.")

    if len(images) != len(scene_audios):
        raise Exception(
            "이미지 개수와 Scene MP3 개수가 다릅니다."
        )

    clips = []

    for image, scene_audio in zip(
        images,
        scene_audios,
    ):

        audio = AudioFileClip(scene_audio)

        duration = audio.duration

        audio.close()

        clip = build_kenburns_clip(
            image,
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