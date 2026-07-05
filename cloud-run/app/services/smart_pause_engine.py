import re

DEFAULT_SENTENCE_PAUSE_SECONDS = 0.4
DEFAULT_COMMA_PAUSE_SECONDS = 0.15


def _break_tag(seconds: float) -> str:
    return f'<break time="{seconds}s" />'


def apply_smart_pause(
    text: str,
    sentence_pause: float = DEFAULT_SENTENCE_PAUSE_SECONDS,
    comma_pause: float = DEFAULT_COMMA_PAUSE_SECONDS,
) -> str:
    """
    문장 부호를 기준으로 자연스러운 pause 마크업을 삽입한 새 문자열을
    반환합니다. 입력 text는 변경하지 않는 순수 함수입니다.

    ElevenLabs가 <break time="Xs" /> 마크업을 text 필드 안에서 그대로
    해석하므로, provider 코드 변경 없이 적용 가능합니다.
    """

    if not text:
        return text

    result = re.sub(
        r"([.!?])\s+",
        lambda m: f"{m.group(1)} {_break_tag(sentence_pause)} ",
        text,
    )

    result = re.sub(
        r"(,)\s+",
        lambda m: f"{m.group(1)} {_break_tag(comma_pause)} ",
        result,
    )

    return result.strip()
