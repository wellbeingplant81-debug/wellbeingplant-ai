import glob
import os

from moviepy import AudioFileClip, concatenate_videoclips
from app.services.kenburns import build_kenburns_clip


def build_video(project_path: str):

    image_folder = os.path.join(project_path, "images")

    audio_path = os.path.join(
        project_path,
        "audio",
        "voice.mp3",
    )

    audio = AudioFileClip(audio_path)

    images = sorted(
        glob.glob(
            os.path.join(image_folder, "*.png")
        )
    )

    if not images:
        raise Exception("이미지가 없습니다.")

    image_duration = audio.duration / len(images)

    clips = []

    for image in images:

        clip = build_kenburns_clip(
            image,
            image_duration,
        )

        clips.append(clip)

    final = concatenate_videoclips(clips)

    video_folder = os.path.join(project_path, "video")
    os.makedirs(video_folder, exist_ok=True)

    output_path = os.path.join(
        video_folder,
        "short.mp4",
    )

    final.write_videofile(
        output_path,
        fps=30,
    )

    audio.close()
    final.close()

    return output_path