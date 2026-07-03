import json
import os
from datetime import timedelta


def format_srt_time(seconds: float) -> str:
    td = timedelta(seconds=seconds)

    total_seconds = int(td.total_seconds())

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int((seconds - total_seconds) * 1000)

    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def split_subtitle(text: str, max_chars: int = 18):
    words = text.split()

    if len(text) <= max_chars:
        return text

    line1 = ""
    line2 = ""

    for word in words:

        if len(line1 + " " + word) <= max_chars:
            line1 = (line1 + " " + word).strip()
        else:
            line2 = (line2 + " " + word).strip()

    return line1 + "\n" + line2


def create_subtitle(project_path: str):

    json_path = os.path.join(
        project_path,
        "script.json",
    )

    with open(
        json_path,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    scenes = data["scenes"]

    subtitle_folder = os.path.join(
        project_path,
        "subtitle",
    )

    os.makedirs(
        subtitle_folder,
        exist_ok=True,
    )

    srt_path = os.path.join(
        subtitle_folder,
        "subtitle.srt",
    )

    total_duration = 45
    scene_duration = total_duration / len(scenes)

    current = 0

    with open(
        srt_path,
        "w",
        encoding="utf-8",
    ) as srt:

        for idx, scene in enumerate(scenes, start=1):

            start = current
            end = current + scene_duration

            srt.write(f"{idx}\n")
            srt.write(
                f"{format_srt_time(start)} --> {format_srt_time(end)}\n"
            )
            srt.write(
                split_subtitle(scene["narration"])
            )
            srt.write("\n\n")

            current = end

    return srt_path