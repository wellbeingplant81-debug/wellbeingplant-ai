"""
Sprint52 - Speech Normalization Engine.

TTS 합성 직전에만 사용할 발음 정규화 문자열을 만듭니다. "2번"처럼
자막/narration에는 자연스러운 숫자 표기지만 기계가 그대로 읽으면
어색한 구간을, 실제 사람이 읽는 발음("두 번")으로 바꿔치기합니다.

Rule 기반(정규식 + 사전)입니다 - LLM 호출이 전혀 없고, 순수 함수라
입력이 같으면 항상 같은 결과를 반환합니다.

주의: 이 함수의 반환값은 TTS 호출에만 사용합니다. script.json의
scene["narration"], 자막(subtitle_service.py), AI 품질 평가에는
항상 원본 narration을 그대로 사용해야 합니다 - voice_quality_engine.
optimize_for_tts()가 이미 지키고 있는 것과 동일한 원칙입니다.
"""

import re

# 고유어(하나/둘/셋...) 수 관형사 - "번/명/개/시간"처럼 고유어 수사로
# 세는 단위에 사용합니다.
_NATIVE_ONES = {
    0: "", 1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯",
    6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉",
}
_NATIVE_TENS = {
    0: "", 1: "열", 2: "스물", 3: "서른", 4: "마흔", 5: "쉰",
    6: "예순", 7: "일흔", 8: "여든", 9: "아흔",
}

# 한자어(일/이/삼/사...) 수사 - "%/km/kg"처럼 한자어 수사로 세는
# 단위에 사용합니다.
_SINO_DIGITS = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_SINO_PLACE_UNITS = ["", "십", "백", "천"]

# 단위(표기 그대로) -> (수사 체계, 실제로 읽을 단위 이름).
# 새 단위를 지원하려면 이 dict에 한 줄만 추가하면 됩니다 - 정규식/
# 변환 로직은 전부 이 표에서 파생됩니다.
UNIT_READINGS = {
    "번": ("native", "번"),
    "명": ("native", "명"),
    "개": ("native", "개"),
    "시간": ("native", "시간"),
    "%": ("sino", "퍼센트"),
    "km": ("sino", "킬로미터"),
    "kg": ("sino", "킬로그램"),
}


def _native_number(n: int) -> str:
    """1~99 범위의 정수를 고유어 수 관형사로 읽습니다 (예: 1->한, 20->스무)."""

    tens, ones = divmod(n, 10)

    if tens == 0:
        return _NATIVE_ONES[ones]

    if ones == 0:
        return "스무" if tens == 2 else _NATIVE_TENS[tens]

    return _NATIVE_TENS[tens] + _NATIVE_ONES[ones]


def _sino_number(n: int) -> str:
    """0~9999 범위의 정수를 한자어 수사로 읽습니다 (예: 10->십, 5->오)."""

    if n == 0:
        return "영"

    digits = str(n)
    length = len(digits)
    result = ""

    for index, char in enumerate(digits):
        digit = int(char)
        place = length - index - 1

        if digit == 0:
            continue

        if place == 0:
            result += _SINO_DIGITS[digit]
        elif digit == 1:
            # 10 -> "십" (X "일십"), 11 -> "십일" - 십 단위 자릿수가
            # 1일 때는 "일"을 생략합니다.
            result += _SINO_PLACE_UNITS[place]
        else:
            result += _SINO_DIGITS[digit] + _SINO_PLACE_UNITS[place]

    return result


def _read_number(number: int, system: str) -> str:
    return _native_number(number) if system == "native" else _sino_number(number)


_UNIT_PATTERN = re.compile(
    r"(\d+)("
    + "|".join(re.escape(unit) for unit in sorted(UNIT_READINGS, key=len, reverse=True))
    + r")(?![a-zA-Z])"
)


def _replace_match(match: "re.Match") -> str:

    number = int(match.group(1))
    unit = match.group(2)
    system, reading_word = UNIT_READINGS[unit]

    return f"{_read_number(number, system)} {reading_word}"


def normalize_for_speech(text: str) -> str:
    """
    "1번"/"5%"/"10km"처럼 숫자+단위로 붙어 있는 표기를 자연스러운
    한국어 발음 문자열로 바꿉니다. 알려진 단위가 없으면 입력을 그대로
    반환합니다 (no-op). 순수 함수 - 입력 문자열을 변경하지 않습니다.
    """

    if not text:
        return text

    return _UNIT_PATTERN.sub(_replace_match, text)
