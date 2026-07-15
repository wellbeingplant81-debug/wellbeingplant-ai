"""
Sprint102-2 - Style Boilerplate Strip.

image_prompt는 Imagen 생성용으로 항상 같은 스타일 문구(실측 예:
"warm, soft, clean wellness aesthetic, natural morning lighting,
minimal composition, cinematic feel.")가 접미사로 붙는다. video_
search_planner.py의 카테고리 매칭이 narration 대신 image_prompt를
보게 되면서(Sprint102-1), 이 스타일 문구 안의 흔한 단어(morning/
wellness 등)가 실제 장면 내용과 무관하게 매번 매칭돼버리는 문제가
실측됐다(2026-07-14 Production QA - scene 내용이 과일주스/간 대사/
영양성분표 읽기였는데도 "daily lifestyle routine" 같은 무관한
Fallback 검색어가 매번 시도됨).

이 모듈은 image_prompt에서 스타일/화질/조명 관련 상투어만 제거하고
장면의 실제 의미(피사체/행동/배경)는 그대로 남기는 순수 함수 하나만
제공한다. 특정 스타일 프롬프트 문구가 나중에 바뀌거나 추가돼도(예:
"golden hour"가 새로 붙거나 "wellness aesthetic"이 다른 표현으로
바뀌어도) STYLE_PHRASES/STYLE_WORDS 목록만 갱신하면 되고, video_
search_planner.py를 포함한 다른 모듈은 전혀 건드릴 필요가 없다 -
"의미 분석(카테고리 매칭)"과 "스타일 제거"의 책임을 분리한다.

이 파일이 하지 않는 것:
- 검색어 생성(video_search_planner.py 소관)
- VideoIntent/Motion Contract/Asset Selection/Visual Relevance 판단
  (전혀 건드리지 않는다 - 이 계층은 순수 텍스트 전처리만 한다)
- 네트워크/Gemini 호출(순수 함수 - 결정적, mock 없이 유닛테스트 가능)
"""

import re


# Sprint102-2 - 여러 단어로 이뤄진 상투어 구. 먼저 통째로 제거해야
# "wellness aesthetic"의 "wellness"가 단어 단위 제거 단계 전에 이미
# 사라진다(구 제거를 단어 제거보다 먼저 적용하는 이유).
STYLE_PHRASES = [
    "wellness aesthetic",
    "natural morning lighting",
    "natural lighting",
    "morning lighting",
    "cinematic lighting",
    "golden hour",
    "high quality",
    "ultra detailed",
    "minimal composition",
    "cinematic feel",
    "warm natural lighting",
    "soft daylight",
    "studio lighting",
    "dramatic light",
    "warm indoor",
    "cool ambient",
]

# Sprint102-2 - 한 단어짜리 상투어. 단어 경계 매칭으로만 제거한다
# (예: "warm"은 지우되 "warming"/"warmth"는 건드리지 않는다) - 부분
# 문자열 치환은 의미 있는 다른 단어를 훼손할 수 있다.
STYLE_WORDS = {
    "warm",
    "soft",
    "clean",
    "cinematic",
    "minimal",
    "aesthetic",
    "detailed",
    "backlit",
}


def strip_style_boilerplate(image_prompt: str) -> str:
    """
    image_prompt(원본 문자열)를 변경하지 않는 순수 함수. 스타일/화질/
    조명 상투어를 제거한 소문자 "의미 프롬프트" 문자열을 반환한다.
    원본에 없던 의미를 추가하지 않고, 상투어가 아닌 단어의 순서/철자는
    그대로 보존한다(공백으로만 재조립).
    """

    if not image_prompt:
        return ""

    text = image_prompt.lower()

    for phrase in sorted(STYLE_PHRASES, key=len, reverse=True):
        text = text.replace(phrase, " ")

    words = re.findall(r"[a-z0-9']+", text)

    semantic_words = [word for word in words if word not in STYLE_WORDS]

    return " ".join(semantic_words)
