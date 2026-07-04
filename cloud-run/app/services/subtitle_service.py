import glob
import json
import os
import re
from datetime import timedelta

from moviepy import AudioFileClip


MAX_CHARS = 18


def format_srt_time(seconds: float):

    td = timedelta(seconds=seconds)

    total = int(td.total_seconds())

    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60

    ms = int((seconds - total) * 1000)

    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def split_subtitle(text: str):

    text = text.strip()

    if not text:
        return []

    result = []

    # 문장 단위 우선 분리
    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        # 짧으면 그대로 사용
        if len(sentence) <= MAX_CHARS:
            result.append(sentence)
            continue

        # 쉼표 기준 분리
        comma_parts = re.split(
            r"(?<=,)\s*",
            sentence,
        )

        for part in comma_parts:

            part = part.strip()

            if not part:
                continue

            if len(part) <= MAX_CHARS:
                result.append(part)
                continue

            # 너무 길면 공백 기준 분리
            words = part.split()

            current = ""

            for word in words:

                candidate = (
                    word
                    if not current
                    else current + " " + word
                )

                if len(candidate) <= MAX_CHARS:
                    current = candidate
                else:

                    if current:
                        result.append(current)

                    current = word

            if current:
                result.append(current)

    return result


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

    scene_audio_folder = os.path.join(
        project_path,
        "audio",
        "scenes",
    )

    scene_audios = sorted(
        glob.glob(
            os.path.join(
                scene_audio_folder,
                "*.mp3",
            )
        )
    )

    if len(scene_audios) != len(scenes):

        raise Exception(
            "Scene MP3 개수와 Scene 개수가 다릅니다."
        )

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

    current = 0
    index = 1

    with open(
        srt_path,
        "w",
        encoding="utf-8",
    ) as srt:

        for scene, audio_path in zip(
            scenes,
            scene_audios,
        ):

            narration = scene["narration"].strip()

            print("\n" + "=" * 60)
            print("NARRATION")
            print(narration)

            subtitles = split_subtitle(
                narration
            )

            print("GENERATED SUBTITLES")
            print(subtitles)
            print("=" * 60)

            audio = AudioFileClip(
                audio_path
            )

            scene_duration = audio.duration

            audio.close()

            lengths = [
                max(1, len(x))
                for x in subtitles
            ]

            total_len = sum(lengths)

            local_time = 0

            for subtitle, length in zip(
                subtitles,
                lengths,
            ):

                part_duration = (
                    scene_duration
                    * length
                    / total_len
                )

                start = current + local_time
                end = start + part_duration

                srt.write(f"{index}\n")

                srt.write(
                    f"{format_srt_time(start)} --> {format_srt_time(end)}\n"
                )

                srt.write(
                    subtitle
                )

                srt.write("\n\n")

                local_time += part_duration
                index += 1

            current += scene_duration

    print(f"\nSRT SAVED : {srt_path}")

    return srt_path