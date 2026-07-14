import re

FILLER_PHRASES = [
    "ultra realistic",
    "photorealistic",
    "cinematic photography",
    "documentary style",
    "professional photography",
    "magazine quality",
    "correct human anatomy",
    "correct anatomy",
    "natural facial expressions",
    "natural facial expression",
    "highly detailed",
    "8k quality",
    "shallow depth of field",
    "vertical composition 9:16",
    "warm natural lighting",
    "no text",
    "no watermark",
    "no logo",
    "no illustration",
    "no cartoon",
    "no cgi",
]

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "is",
    "are", "to", "as", "her", "his", "their", "she", "he", "they", "it",
    "while", "for", "by", "into", "onto", "from", "that", "this", "be",
    "being", "was", "were",
}

DEFAULT_MAX_WORDS = 8


def _clean_words(image_prompt: str) -> list:

    text = image_prompt.lower()

    for phrase in FILLER_PHRASES:
        text = text.replace(phrase, " ")

    text = re.sub(r"[^a-z0-9\s]", " ", text)

    return [
        word
        for word in text.split()
        if word and word not in STOPWORDS
    ]


def extract_search_query(
    image_prompt: str,
    max_words: int = DEFAULT_MAX_WORDS,
) -> str:
    """
    Imagen용 상세 image_prompt에서 Pexels/Pixabay 검색에 적합한 핵심
    영어 키워드 구를 추출합니다. 원본 image_prompt는 변경하지 않는
    순수 함수입니다 (스타일/화질 관련 상투어를 제거하고, 불용어를
    걷어낸 뒤 앞쪽 핵심 단어 max_words개만 남깁니다).
    """

    if not image_prompt:
        return ""

    return " ".join(_clean_words(image_prompt)[:max_words])


# Sprint100-4 - Visual Intelligence Completion: Scene Intent 기반 검색어.
# extract_search_query()는 항상 문장 맨 앞 max_words개만 남기므로,
# 문장 뒷부분에 있는 핵심 명사가 통째로 잘려 나가는 문제가 실측됐다
# (2026-07-14 Production QA: food scene image_prompt "A high-angle shot
# showing a person's hands pushing away ... to reach for a vibrant bowl
# of fresh salad with spinach and sliced bananas..."에서 검색어가
# "high angle shot showing person s hands pushing"으로 잘려, 정작
# salad/spinach/bananas가 전부 유실됨). visual_intent별로 문장 내
# 위치와 무관하게 우선 배치할 핵심 단어 목록이다 - motion_contract.py의
# INTENT_MEDICAL/INTENT_LIFESTYLE 값과 매칭된다(INTENT_GENERAL은 별도
# 우선순위 없이 기존 동작과 동일).
INTENT_PRIORITY_KEYWORDS = {
    "medical": [
        "artery", "arteries", "vessel", "vessels", "blood", "organ",
        "organs", "brain", "nerve", "nerves", "cell", "cells", "anatomy",
        "medical", "diagram", "cross", "section", "inflammation", "plaque",
    ],
    "lifestyle": [
        "walking", "walk", "jogging", "jog", "run", "running", "park",
        "exercise", "outdoor", "workout", "hospital", "doctor", "patient",
        "meal", "food", "salad", "vegetable", "vegetables", "fruit",
        "fruits", "kitchen", "plate", "diet", "spinach", "banana",
        "bananas", "snack", "snacks", "healthy",
    ],
}


def extract_intent_aware_search_query(
    image_prompt: str,
    visual_intent: str = None,
    max_words: int = DEFAULT_MAX_WORDS,
) -> str:
    """
    extract_search_query()와 동일한 정제(상투어/불용어 제거)를 거친
    뒤, visual_intent에 대응하는 INTENT_PRIORITY_KEYWORDS에 속한
    단어가 있으면 문장 내 위치와 무관하게 앞쪽으로 끌어올린다. 순서가
    바뀔 뿐 단어 자체를 새로 만들지는 않는 순수 함수다.

    visual_intent가 None이거나 INTENT_PRIORITY_KEYWORDS에 없는 값
    (예: motion_contract.INTENT_GENERAL)이거나, 우선순위 단어가
    문장에 하나도 없으면 extract_search_query()와 100% 동일한 결과를
    반환한다 - 완전히 하위 호환.
    """

    if not image_prompt:
        return ""

    words = _clean_words(image_prompt)

    priority_vocab = set(INTENT_PRIORITY_KEYWORDS.get(visual_intent, []))

    priority_words = [word for word in words if word in priority_vocab]
    remaining_words = [word for word in words if word not in priority_vocab]

    seen = set()
    ordered = []
    for word in priority_words + remaining_words:
        if word not in seen:
            seen.add(word)
            ordered.append(word)

    return " ".join(ordered[:max_words])
