import json
import os
from datetime import timedelta


TOTAL_DURATION = 45.0
MIN_DURATION = 2.0
MAX_DURATION = 8.0
MAX_CHARS = 14


def format_srt_time(seconds: float) -> str:

    td = timedelta(seconds=seconds)

    total_seconds = int(td.total_seconds())

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int((seconds - total_seconds) * 1000)

    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def split_subtitle(text: str):

    if len(text) <= MAX_CHARS:
        return text

    # 문장 부호 우선 분리
    for token in [", ", ". ", " 그리고 ", " 하지만 ", " 그래서 ", " 때문에 "]:

        if token in text:
            left, right = text.split(token, 1)

            if len(left) <= MAX_CHARS:
                return left + token.strip() + "\n" + right

    # 가운데 기준 분리
    mid = len(text) // 2

    left = text[:mid]
    right = text[mid:]

    idx = left.rfind(" ")

    if idx != -1:
        return left[:idx] + "\n" + left[idx + 1:] + right

    return left + "\n" + right


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

    lengths = [
        len(scene["narration"])
        for scene in scenes
    ]

    total_length = sum(lengths)

    durations = []

    for length in lengths:

        duration = TOTAL_DURATION * (length / total_length)

        duration = max(MIN_DURATION, duration)
        duration = min(MAX_DURATION, duration)

        durations.append(duration)

    # 총 시간이 45초가 되도록 비율 보정
    scale = TOTAL_DURATION / sum(durations)

    durations = [
        d * scale
        for d in durations
    ]

    current = 0

    with open(
        srt_path,
        "w",
        encoding="utf-8",
    ) as srt:

        for idx, scene in enumerate(scenes, start=1):

            start = current
            end = current + durations[idx - 1]

            srt.write(f"{idx}\n")
            srt.write(
                f"{format_srt_time(start)} --> {format_srt_time(end)}\n"
            )

            srt.write(
                split_subtitle(
                    scene["narration"]
                )
            )

            srt.write("\n\n")

            current = end

    return srt_path