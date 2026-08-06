"""
Sprint76 - 스톡 검색어를 요소에서 만든다.

기존 extract_search_query는 image_prompt 문장에서 불용어를 걷어내고 앞
8단어를 잘라 썼다. 축적된 스톡 scene 140건에서 검색어는 예외 없이 정확히
8단어였다 - 100%가 상한에 걸렸다는 뜻이고, 프롬프트 단어를 덮는 비율은
평균 15.2%였다.

Sprint75가 파생 image_prompt의 순서를 subject 우선으로 바꾸면서 상당
부분이 이미 나아졌다. 예전 검색어는 단어의 36.9%가 카메라 어휘였는데
("wide shot", "top down view" - Pexels는 사진을 앵글로 색인하지 않는다)
지금은 앞쪽이 피사체로 채워진다.

여기서 고치는 것은 남은 문제다. 검색어가 여전히 "문장에서 앞 N단어"라
중복 단어가 예산을 두 번씩 먹고("clear glass water lukewarm water poured
glass gentle"), 검색이 0건이어도 다른 표현을 시도하지 않는다.

요소가 있으면 subject/action/environment만 쓴다. camera/composition/
lighting은 그림을 그릴 때 필요한 지시이지 사진을 찾는 말이 아니다.
"""

from app.services.search_query_extractor import STOPWORDS, extract_search_query


# 검색어 상한. 기존 8단어와 같게 두되, 이제는 요소에서 고른 단어들이라
# 같은 예산으로 더 많은 정보가 들어간다.
MAX_QUERY_WORDS = 8

# 검색어에 쓰는 요소. 순서가 곧 우선순위다 - 예산이 모자라면 뒤가
# 잘린다.
QUERY_ELEMENTS = ("subject", "action", "environment")

# 확장 단계에서 남기는 최소 단어 수.
_HEAD_WORDS = 3


def _words(text: str) -> list:
    """소문자 단어들. 불용어와 기호를 걷어낸다."""

    if not text:
        return []

    cleaned = "".join(
        char if char.isalnum() or char.isspace() else " "
        for char in str(text).lower()
    )

    return [
        word for word in cleaned.split()
        if word and word not in STOPWORDS
    ]


def _element_words(scene: dict) -> list:
    """요소에서 단어를 순서대로, 중복 없이 모은다."""

    collected = []
    seen = set()

    for element in QUERY_ELEMENTS:
        for word in _words(scene.get(element)):
            if word not in seen:
                seen.add(word)
                collected.append(word)

    return collected


def build_query(scene: dict, max_words: int = MAX_QUERY_WORDS) -> str:
    """
    scene 하나의 검색어. 순수 함수입니다.

    요소가 없는 구버전 scene은 기존 extract_search_query로 넘긴다 -
    그쪽 동작은 한 글자도 바뀌지 않는다.
    """

    scene = scene or {}
    words = _element_words(scene)

    if not words:
        return extract_search_query(
            scene.get("image_prompt", ""), max_words=max_words,
        )

    return " ".join(words[:max_words])


def expand(scene: dict, max_words: int = MAX_QUERY_WORDS) -> list:
    """
    좁은 검색어에서 넓은 검색어로 물러나는 후보 목록. 순수 함수입니다.

    스톡 검색은 어휘가 조금만 어긋나도 0건이 나온다. 지금은 그러면
    바로 AI 폴백인데, 표현을 넓혀 몇 번 더 시도할 값이 있다.

    앞에서부터 단어를 덜어낸다 - subject가 앞에 있으므로 뒤에서 덜어야
    피사체가 남는다.
    """

    scene = scene or {}
    words = _element_words(scene)

    if not words:
        primary = build_query(scene, max_words)
        return [primary] if primary else []

    candidates = []
    length = min(len(words), max_words)

    while length >= 1:
        candidate = " ".join(words[:length])

        if candidate not in candidates:
            candidates.append(candidate)

        if length <= _HEAD_WORDS:
            break

        # 절반씩 줄인다. 한 단어씩 줄이면 사실상 같은 검색을 여러 번
        # 하게 되고, Pexels 결과는 그만큼 촘촘하게 달라지지 않는다.
        length = max(_HEAD_WORDS, length // 2)

    return candidates
