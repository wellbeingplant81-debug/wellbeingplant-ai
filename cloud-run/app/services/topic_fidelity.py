"""
Sprint95 - Topic Fidelity (Epic 48).

사용자가 적은 주제가 영상 끝까지 남아 있는지 본다.

착수 계기는 "아침 공복 물"로 시킨 영상이 "커피" 영상으로 나온 사례였다.
그런데 그 프로젝트의 project.json을 열어 보니 주제가 이렇게 저장돼
있었다.

    topic: '?? ??? ? ? ?? ????? ?? ??'

PV-02에서 요청을 보낼 때 charset을 지정하지 않아 한글이 물음표로
바뀐 것이다. Writer는 주제를 아예 받지 못한 상태에서 대본을 썼고,
빈 자리를 스스로 채웠다. 대본 엔진이 주제를 바꾼 것이 아니다.

주제가 온전한 프로젝트 29편을 다시 재 봤다.

    제목에 주제어가 하나도 없음   1 / 29  (3%)
    본문에 주제어가 하나도 없음   0 / 29  (0%)

그래서 이 모듈이 막는 것은 두 가지다.

  1. 주제가 비었거나 알아볼 수 없으면 Writer를 부르기 전에 멈춘다.
     실제로 사고가 난 지점이 여기다 - 빈 주제를 받은 모델은 반드시
     무언가를 지어낸다.

  2. 만들어진 대본의 제목이 주제를 담고 있는지 확인한다. 담고 있지
     않으면 게이트가 다시 만들게 한다.

주제어에서는 내용어를 전부 본다. korean_noun_filter(Sprint94)는 조사가
붙어 나타난 적이 있는지를 명사의 증거로 요구하는데, 그것은 긴 대본에는
맞지만 사람이 쓴 짧은 주제구에는 맞지 않는다 - "당뇨 예방에 좋은 아침
식사"에서 "당뇨"와 "아침"에는 조사가 붙지 않아 통째로 빠진다(실측에서
제목에 "당뇨"가 뻔히 있는데 이탈로 잘못 세었다).

AI를 부르지 않는다. 규칙과 문자열 비교뿐이다.
"""

import re
from typing import List

from app.services import korean_noun_filter as nf

_TOKEN = re.compile(r"[가-힣]{2,}")

# 글자나 숫자가 하나도 없으면 Writer가 채울 것이 없다.
#
# "한글이 있어야 한다"로 만들었다가 되돌렸다. 실제로 사고를 낸 것은
# 영문이 아니라 "?? ??? ? ?"처럼 글자가 통째로 사라진 문자열이고,
# 한글을 강제하면 "vitamin D" 같은 멀쩡한 주제까지 막힌다.
_WORD_CHARACTER = re.compile(r"[0-9A-Za-z가-힣]")


class TopicError(ValueError):
    """주제를 알아볼 수 없다. Writer를 부르기 전에 멈춘다."""


def _one_character_stem(word: str) -> bool:
    """조사나 어미를 떼면 한 글자만 남는가."""

    for suffix in sorted(nf._PARTICLES + nf._VERBAL_TAILS, key=len, reverse=True):
        if word.endswith(suffix) and len(word) - len(suffix) == 1:
            return True
    return False


def topic_keywords(topic: str) -> List[str]:
    """주제어의 내용어. 조사만 떼고 기능어만 거른다."""

    words = []

    for token in _TOKEN.findall(topic or ""):
        if token in nf._FUNCTION_WORDS:
            continue

        stem = nf._strip_particles(token)

        # 어간이 한 글자면 통째로 버린다.
        #
        # "잔이"는 조사를 떼면 "잔"(한 글자)이 되는데, 어간 최소 길이가
        # 2라서 조사가 떨어지지 않고 "잔이"가 그대로 남는다. 그러면
        # 제목의 "물 한 잔"과 영영 안 맞는다 - 있으나 마나가 아니라
        # 없는 것만 못하다(실측: 잔이/질에/주는/미치).
        if _one_character_stem(stem):
            continue

        if len(stem) < 2:
            continue
        if stem in nf._FUNCTION_WORDS or nf._looks_verbal(stem):
            continue
        if stem not in words:
            words.append(stem)

    return words


def validate_topic(topic: str) -> List[str]:
    """
    주제가 쓸 만한지 본다. 아니면 던진다.

    조용히 넘기지 않는 이유가 있다. 빈 주제를 받은 모델은 반드시
    무언가를 지어내고, 그 대본으로 이미지 6장과 음성과 영상이
    만들어진다 - 아무도 시키지 않은 주제로. 여기서 멈추는 편이
    훨씬 싸다.
    """

    if not topic or not topic.strip():
        raise TopicError("주제가 비어 있습니다.")

    if not _WORD_CHARACTER.search(topic):
        raise TopicError(
            f"주제에서 글자를 찾을 수 없습니다: {topic!r}. "
            "요청이 UTF-8로 전달됐는지 확인하십시오 - 인코딩이 어긋나면 "
            "한글이 물음표로 바뀌어 도착합니다."
        )

    return topic_keywords(topic)


def check(topic: str, data: dict) -> dict:
    """
    만들어진 대본이 주제를 지켰는지. 순수 읽기입니다.

    제목과 본문을 따로 본다 - 본문은 주제를 다루면서 제목만 "이것"으로
    가리는 경우가 실제로 있었고(실측 1/29), 그 둘은 다른 문제다.
    """

    keywords = topic_keywords(topic)

    if not keywords:
        # 잴 수 있는 것이 없으면 통과로 둔다. 못 재는 것과 벗어난 것은
        # 다르다 - 여기서 실패로 처리하면 게이트가 고칠 수 없는 이유로
        # 3번 다시 만든다.
        return {
            "keywords": [], "in_title": [], "in_body": [],
            "title_ok": True, "body_ok": True, "passed": True,
            "measurable": False,
        }

    title = (data.get("title") or "")
    body = data.get("script") or ""
    narration = " ".join(
        (scene.get("narration") or "") for scene in (data.get("scenes") or [])
    )
    text = f"{body} {narration}"

    in_title = [word for word in keywords if word in title]
    in_body = [word for word in keywords if word in text]

    return {
        "keywords": keywords,
        "in_title": in_title,
        "in_body": in_body,
        "title_ok": bool(in_title),
        "body_ok": bool(in_body),
        "passed": bool(in_title) and bool(in_body),
        "measurable": True,
    }
