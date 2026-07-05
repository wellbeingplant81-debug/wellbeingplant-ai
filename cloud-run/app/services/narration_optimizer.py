import re

DEFAULT_MAX_SENTENCE_LENGTH = 40


def _split_long_sentence(sentence: str, max_length: int) -> list:

    if len(sentence) <= max_length:
        return [sentence]

    comma_positions = [m.start() for m in re.finditer(",", sentence)]

    if not comma_positions:
        return [sentence]

    midpoint = len(sentence) / 2
    split_at = min(comma_positions, key=lambda pos: abs(pos - midpoint))

    first = sentence[:split_at].strip().rstrip(",")
    second = sentence[split_at + 1:].strip()

    if not first or not second:
        return [sentence]

    if not first.endswith((".", "!", "?")):
        first += "."

    return [first, second]


def optimize_narration(
    text: str,
    max_sentence_length: int = DEFAULT_MAX_SENTENCE_LENGTH,
) -> str:
    """
    지나치게 긴 문장을 쉼표 위치 기준으로 두 문장으로 재구성한 새
    문자열을 반환합니다. 입력 text는 변경하지 않는 순수 함수입니다.
    (Gemini 등 AI 호출 없이 규칙 기반으로만 동작 - 결정적이고
    단위 테스트가 용이합니다.)
    """

    if not text:
        return text

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    optimized_parts = []

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        optimized_parts.extend(
            _split_long_sentence(sentence, max_sentence_length)
        )

    return " ".join(optimized_parts)
