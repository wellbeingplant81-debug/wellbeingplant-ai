import glob
import json
import os
import re
import unicodedata
from datetime import timedelta

from moviepy import AudioFileClip

from app.services.kenburns import VIDEO_WIDTH
from app.services.subtitle_placement_service import (
    POSITION_TOP,
    choose_subtitle_position,
)
from app.services.video_builder import _resolve_asset_path

# Sprint57 - Smart Subtitle Placement v1. choose_subtitle_position()이
# 고른 "top"/"bottom"을 libass가 SRT 안에서도 그대로 해석하는 ASS
# override tag로 바꾼다. force_style의 기본 Alignment=2(하단)는
# final_video_service.py에서 그대로 유지하고, 상단으로 골라진 scene의
# cue에만 {\an8}을 앞에 붙여 그 cue만 상단으로 덮어쓴다.
_POSITION_TAGS = {
    POSITION_TOP: r"{\an8}",
}
_DEFAULT_POSITION_TAG = r"{\an2}"


MAX_CHARS = 18
MIN_CHARS = 4

# Sprint39 - Semantic Subtitle Engine.
#
# 실측 보정(2026-07-06): final_video_service.py와 동일한 force_style
# (FontName=Malgun Gothic, FontSize=22, Bold=1, Outline=4)로 1080x1920
# 검정 배경에 순수 한글 자막을 실제로 렌더링한 뒤, 흰 글자의 픽셀
# bounding box를 직접 측정했다(폰트 메트릭 API가 아니라 libass가 실제로
# 그린 결과를 측정 - PlayRes 관련 내부 스케일링까지 그대로 반영됨).
#
#   한글 3자 "가나다"  -> 320px  (약 106.7px/자)
#   한글 10자(공백 없음) -> 1080px에서 이미 꽉 참(경계)
#
# 즉 전각(한글) 1자 ≈ 107px, 이 모듈의 폭 단위(_display_width, 전각=2)
# 기준으로 1 unit ≈ 53.5px다. 이전 값(SAFE_AREA_MAX_LINE_WIDTH=34)은
# 이 실측 없이 잡은 추정치라 실제보다 훨씬 관대해서(실제 렌더링
# 프레임에서 좌우 잘림 발생) 아래처럼 다시 계산한다.
_MEASURED_PX_PER_UNIT = 53.5

# 화면 폭 중 자막에 실제로 쓸 안전 영역 비율(좌우 각 7.5% 여백).
SAFE_AREA_WIDTH_RATIO = 0.85

# 화면 1줄 안전 영역에 들어갈 수 있는 최대 표시 폭(전각=2/반각=1 단위,
# _display_width 참고) - VIDEO_WIDTH가 바뀌어도(예: 다른 해상도)
# 자동으로 다시 계산되도록 상수가 아니라 계산식으로 둔다.
SAFE_AREA_MAX_LINE_WIDTH = int(
    VIDEO_WIDTH * SAFE_AREA_WIDTH_RATIO / _MEASURED_PX_PER_UNIT
)

MAX_LINES_PER_CUE = 2

# _split_sentence_by_words()에 넘길 조각 상한(문자 수 기준). 최악의
# 경우(공백 없이 한글만 이어지는 경우, 1글자=2 unit)를 가정해 2줄 폭
# 예산을 문자 수로 보수적으로 환산한다 - 실제 문장은 단어 사이 공백이
# 섞여 있어 이보다 조금 더 들어가는 경우가 많지만, 안전한 쪽으로
# 잡는다(넘치는 것보다 조각이 하나 더 생기는 편이 낫다).
CUE_GROUPING_MAX_CHARS = (SAFE_AREA_MAX_LINE_WIDTH * MAX_LINES_PER_CUE) // 2

# 균형 분할 후보 중, 마지막 줄이 단어 1개뿐이고 표시 폭이 이 값
# 이하이면 "조사만 혼자 남은 것"으로 보고 그 분할은 피한다.
MIN_ORPHAN_LINE_WIDTH = 6

QUOTE_CHARS = set("'\"‘’“”")

# 다음 줄 맨 앞에 오면 자연스러운 접속사/접속부사 - 이 앞에서 끊는
# 분할을 우선한다.
CONJUNCTIONS = {
    "그리고", "그러나", "하지만", "그래서", "또한", "그런데", "즉",
    "따라서", "또", "그러면", "그러므로", "왜냐하면", "반면에", "게다가",
}


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

    Sprint39: 조각 하나의 상한을 MAX_CHARS(1줄 분량)가 아니라
    CUE_GROUPING_MAX_CHARS(약 2줄 분량)로 넉넉하게 잡는다 - 실제 화면
    줄바꿈은 create_subtitle()에서 wrap_to_safe_lines()가 별도로
    결정하므로, 여기서는 예전보다 더 잘게 쪼개질 필요가 없다.
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
        if len(sentence) <= CUE_GROUPING_MAX_CHARS:
            result.append(sentence)
            continue

        result.extend(_split_sentence_by_words(sentence, CUE_GROUPING_MAX_CHARS))

    return result


def _display_width(text: str) -> int:
    """
    전각(한글 등 East Asian Wide/Fullwidth) 문자는 2, 그 외(영문/숫자/
    기호 등 narrow/halfwidth/neutral)는 1로 계산한 표시 폭 근사치.
    실제 폰트 파일을 렌더링해 재는 게 아니라(배포 환경에 폰트가 없을
    수 있어 이식성이 떨어짐), 표준 라이브러리(unicodedata)만으로
    한글/영문 폭 차이를 반영한다.
    """

    width = 0

    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ("W", "F") else 1

    return width


def _quote_open_after_each_word(words: list) -> list:
    """
    각 단어 뒤 시점에 따옴표가 열린 채로 남아있는지 여부를 반환한다.
    단어 하나에 따옴표가 홀수 개 있으면 그 단어에서 열림/닫힘 상태가
    뒤집힌다고 본다 - "'이"에서 열리고 "물'"에서 닫히는 식으로, 같은
    구를 감싼 따옴표를 문자 단위가 아니라 단어 단위로 추적한다.
    """

    states = []
    inside = False

    for word in words:

        quote_count = sum(1 for ch in word if ch in QUOTE_CHARS)

        if quote_count % 2 == 1:
            inside = not inside

        states.append(inside)

    return states


def wrap_to_safe_lines(text: str, max_line_width: int = SAFE_AREA_MAX_LINE_WIDTH) -> str:
    """
    Sprint39 - Semantic Subtitle Engine.

    자막 조각 하나를 화면 Safe Area 안에 들어가는 최대
    MAX_LINES_PER_CUE(2)줄로 나눕니다. 이미 한 줄에 들어가면 그대로
    반환합니다. 단어 경계에서만 끊고(음절 단위 분할 절대 없음), 여러
    분할 후보 중 아래 우선순위로 고릅니다(우선순위가 앞설수록 먼저
    적용, 그 다음 기준은 동점일 때만 사용):

    1. 조사 고아 방지: 마지막 줄이 단어 1개뿐이고 너무 짧으면 피한다.
    2. 쉼표: 앞 줄이 쉼표로 끝나는 지점을 우선한다.
    3. 따옴표: 따옴표로 감싼 구를 두 줄로 쪼개는 지점은 피한다.
    4. 접속사: 다음 줄이 접속사로 시작하는 지점을 우선한다.
    5. 균형: 위 조건이 모두 동률이면 두 줄의 표시 폭 차이가 가장
       작은(가장 균형 잡힌) 지점을 고른다.

    두 줄 다 max_line_width 이내로 들어가는 분할이 하나도 없으면(단어
    하나가 유독 길거나 등), 단어 경계는 지키되 첫 줄을 최대한 채우는
    방식으로 안전하게 폴백합니다.
    """

    if _display_width(text) <= max_line_width:
        return text

    words = text.split()

    if len(words) <= 1:
        return text

    quote_open_after = _quote_open_after_each_word(words)

    candidates = []

    for i in range(1, len(words)):

        line1 = " ".join(words[:i])
        line2 = " ".join(words[i:])

        width1 = _display_width(line1)
        width2 = _display_width(line2)

        if width1 > max_line_width or width2 > max_line_width:
            continue

        orphan_penalty = 1 if (
            len(words[i:]) == 1 and width2 <= MIN_ORPHAN_LINE_WIDTH
        ) else 0

        comma_penalty = 0 if words[i - 1].rstrip().endswith(",") else 1
        quote_break_penalty = 1 if quote_open_after[i - 1] else 0
        conjunction_penalty = 0 if words[i] in CONJUNCTIONS else 1
        imbalance = abs(width1 - width2)

        score = (
            orphan_penalty,
            comma_penalty,
            quote_break_penalty,
            conjunction_penalty,
            imbalance,
        )

        candidates.append((score, line1, line2))

    if not candidates:
        return _greedy_two_line_fallback(words, max_line_width)

    _best_score, best_line1, best_line2 = min(candidates, key=lambda c: c[0])

    return f"{best_line1}\n{best_line2}"


def _greedy_two_line_fallback(words: list, max_line_width: int) -> str:
    """
    두 줄 다 max_line_width 이내로 들어가는 조합이 하나도 없을 때만
    쓰는 안전 장치. 단어 경계는 지키면서 첫 줄을 최대한 채우고 나머지를
    둘째 줄로 넘긴다 - 둘째 줄이 살짝 넘칠 수 있지만, 단어를 쪼개는
    일은 절대 없다.
    """

    line1_words = []
    width = 0

    for index, word in enumerate(words):

        extra = _display_width(word) + (1 if line1_words else 0)

        if line1_words and width + extra > max_line_width:
            break

        line1_words.append(word)
        width += extra

    if not line1_words:
        line1_words = [words[0]]

    line2_words = words[len(line1_words):]

    if not line2_words:
        return " ".join(line1_words)

    return " ".join(line1_words) + "\n" + " ".join(line2_words)


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

            # Sprint57 - scene 이미지 상/하단 복잡도를 비교해 이
            # scene의 모든 cue에 공통으로 적용할 위치를 한 번만
            # 정한다(scene 안에서 위치가 cue마다 바뀌면 자막이
            # 산만해지므로).
            asset_path = _resolve_asset_path(project_path, scene)
            position = choose_subtitle_position(asset_path)
            position_tag = _POSITION_TAGS.get(position, _DEFAULT_POSITION_TAG)

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
                    position_tag + wrap_to_safe_lines(subtitle)
                )

                srt.write("\n\n")

                local_time += part_duration
                index += 1

            current += scene_duration

    print(f"\nSRT SAVED : {srt_path}")

    return srt_path