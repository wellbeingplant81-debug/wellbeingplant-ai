import glob
import json
import os
import re
from datetime import timedelta

from moviepy import AudioFileClip


MAX_CHARS = 18
MIN_CHARS = 4


def format_srt_time(seconds: float):

    td = timedelta(seconds=seconds)

    total = int(td.total_seconds())

    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60

    ms = int((seconds - total) * 1000)

    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _split_sentence_by_words(sentence: str, max_chars: int):
    """
    문장 하나를 공백(단어/어절) 단위로만 묶어 max_chars 이하의
    자연스러운 조각으로 나눕니다. 쉼표를 우선 분리 기준으로 쓰지
    않으므로 "한 잔," 같은 쉼표 앞의 짧은 절이 단독 조각으로 남지
    않고 다음 단어들과 함께 묶입니다. 글자(음절) 단위 분할은 절대
    하지 않습니다 - 한 단어가 max_chars보다 길어도 그 단어를 쪼개지
    않고 그대로 한 조각으로 둡니다.
    """

    words = sentence.split()

    if not words:
        return []

    groups = []
    current = []
    current_len = 0

    for word in words:

        extra = len(word) + (1 if current else 0)

        if current and current_len + extra > max_chars:
            groups.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += extra

    if current:
        groups.append(" ".join(current))

    # 마지막 조각이 너무 짧은 자투리(예: 쉼표 하나짜리 절)면 바로
    # 앞 조각과 합쳐 의미 있는 단위로 유지한다.
    while len(groups) >= 2 and len(groups[-1]) < MIN_CHARS:
        groups[-2:] = [f"{groups[-2]} {groups[-1]}"]

    return groups


def split_subtitle(text: str):
    """
    narration을 자막 조각으로 나눕니다. 항상 "문장 -> (너무 길면)
    단어 단위 묶음" 순서로만 나누고, 글자(음절) 단위 분할은 하지
    않습니다.
    """

    text = text.strip()

    if not text:
        return []

    result = []

    # 문장 단위 우선 분리 (마침표/물음표/느낌표 기준)
    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        # 짧으면 문장을 그대로 유지한다.
        if len(sentence) <= MAX_CHARS:
            result.append(sentence)
            continue

        result.extend(_split_sentence_by_words(sentence, MAX_CHARS))

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