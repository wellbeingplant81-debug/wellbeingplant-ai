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

    text = image_prompt.lower()

    for phrase in FILLER_PHRASES:
        text = text.replace(phrase, " ")

    text = re.sub(r"[^a-z0-9\s]", " ", text)

    words = [
        word
        for word in text.split()
        if word and word not in STOPWORDS
    ]

    return " ".join(words[:max_words])
