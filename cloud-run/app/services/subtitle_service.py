import json
import math
import os
from datetime import timedelta

from moviepy import AudioFileClip


def format_srt_time(seconds: float):

    td = timedelta(seconds=seconds)

    total = int(td.total_seconds())

    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60

    ms = int((seconds - total) * 1000)

    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def create_subtitle(project_path: str):

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

    scenes = data["scenes"]

    audio_path = os.path.join(
        project_path,
        "audio",
        "voice.mp3",
    )

    audio = AudioFileClip(audio_path)

    total_duration = audio.duration

    audio.close()

    subtitle_dir = os.path.join(
        project_path,
        "subtitle",
    )

    os.makedirs(
        subtitle_dir,
        exist_ok=True,
    )

    srt_path = os.path.join(
        subtitle_dir,
        "subtitle.srt",
    )

    total_chars = sum(
        len(scene["narration"])
        for scene in scenes
    )

    current = 0
    index = 1

    with open(
        srt_path,
        "w",
        encoding="utf-8",
    ) as srt:

        for scene in scenes:

            scene_duration = (
                total_duration
                * len(scene["narration"])
                / total_chars
            )

            subtitles = scene.get(
                "subtitles",
                [scene["narration"]],
            )

            part_duration = (
                scene_duration
                / len(subtitles)
            )

            for subtitle in subtitles:

                start = current
                end = current + part_duration

                srt.write(f"{index}\n")

                srt.write(
                    f"{format_srt_time(start)} --> {format_srt_time(end)}\n"
                )

                srt.write(
                    subtitle.strip()
                )

                srt.write("\n\n")

                current = end
                index += 1

    return srt_path