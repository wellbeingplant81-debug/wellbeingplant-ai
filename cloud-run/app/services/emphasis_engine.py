import re

DEFAULT_PRE_EMPHASIS_PAUSE_SECONDS = 0.15


def apply_emphasis(
    text: str,
    keywords: list,
    pre_pause: float = DEFAULT_PRE_EMPHASIS_PAUSE_SECONDS,
) -> str:
    """
    지정한 keywords 앞에 짧은 pause를 삽입하여 강조 효과를 주는 새
    문자열을 반환합니다. 입력 text는 변경하지 않는 순수 함수입니다.

    한국어는 영문처럼 대문자로 강조할 수 없으므로, 강조어 직전에 짧은
    pause를 두어 주의를 끄는 방식만 사용합니다 (검증되지 않은 음향
    효과이므로 최선노력 수준의 휴리스틱입니다).
    """

    if not text or not keywords:
        return text

    result = text

    for keyword in keywords:

        if not keyword:
            continue

        pattern = re.escape(keyword)

        def _emphasize(match, _pause=pre_pause):
            pause_tag = f'<break time="{_pause}s" />'
            return f"{pause_tag} {match.group(0)}"

        result = re.sub(pattern, _emphasize, result)

    return result
