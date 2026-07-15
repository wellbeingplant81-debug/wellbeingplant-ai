"""
Sprint102 - Video Coverage Intelligence.

Sprint101 Production QA에서 확인된 병목은 VideoIntent 판단이 아니라
검색어 품질이었다: search_query_extractor.extract_search_query()는
image_prompt(AI 이미지 생성용 문장, 예: "medium shot fit korean man
50s walking briskly")에서 검색어를 뽑는데, 이런 "생성형 이미지
프롬프트" 스타일 문장은 실제 스톡 영상 태깅/제목과 잘 맞지 않아
Visual Relevance 점수가 낮게 나온다(실측: 0.2~0.4).

이 모듈은 Primary 검색어 하나에 실패했을 때 시도할 대안 검색어들
(Action -> Fallback -> Broad)을 우선순위 리스트로 만든다. 결정적으로
동작하는 순수 함수다.

이 파일이 하지 않는 것(책임을 섞지 않는다):
- VideoIntent 판단(motion_contract.py 소관)
- Asset 채점/선택(asset_selector.py의 select_with_relevance() 소관,
  threshold/점수 로직 무변경)
- Video Builder 렌더링
- 네트워크/Gemini 호출(순수 함수 - 결정적, mock 없이 유닛테스트 가능)

Sprint102-1 - 카테고리 매칭 신호를 narration(한국어 substring)에서
image_prompt(영어, extract_search_query()와 동일한 정제 파이프라인인
_clean_words()로 토큰화)로 바꿨다. 2026-07-14 Production QA 실측:
narration="문제는 초기 증상이 거의 없다는 겁니다..."(병원/의사/환자
같은 한국어 키워드가 전혀 없음)인데 실제 image_prompt는 "high angle
shot dimly lit hospital room capturing"으로 "hospital"을 명시하고
있었다 - narration 키워드 매칭으로는 카테고리를 하나도 못 찾았지만,
image_prompt 매칭이었다면 hospital 카테고리를 찾을 수 있었다.
image_prompt는 Imagen에 넘기는 상세 영어 묘사라 narration보다 시각적
내용을 더 직접적으로 담고 있다.
"""

from app.services.search_query_extractor import _clean_words, extract_search_query
from app.services.style_boilerplate_stripper import strip_style_boilerplate


# Sprint102 - 카테고리별 "이 내용이면 이런 영어 검색어를 추가로
# 시도해본다"는 검색어 템플릿. english_keywords는 image_prompt를
# _clean_words()로 토큰화한 결과와 정확히 일치하는 단어가 있는지로
# 판정한다(부분 문자열이 아니라 단어 단위 - "walk"가 "walkway" 같은
# 단어 안에 우연히 끼어 있는 오탐을 막는다). action_query는 Primary
# 다음으로 시도할 짧은 동작 중심 검색어이고, fallback_queries는 그
# 다음에 순서대로 시도할, 실제 스톡 영상 라이브러리에서 흔히 쓰이는
# 일반적인 문구들이다.
CATEGORY_QUERY_TEMPLATES = {
    "walking": {
        "english_keywords": ["walk", "walking", "walks", "stroll", "strolling"],
        "action_query": "person walking",
        "fallback_queries": [
            "healthy walking",
            "senior walking",
            "person walking outside",
            "walking exercise",
        ],
    },
    "exercise": {
        "english_keywords": [
            "exercise", "exercising", "workout", "stretching", "fitness", "squat", "squats",
        ],
        "action_query": "person exercising",
        "fallback_queries": [
            "home workout",
            "stretching exercise",
            "fitness training",
            "daily exercise routine",
        ],
    },
    "meal": {
        "english_keywords": [
            "meal", "eating", "food", "cooking", "dining", "vegetables", "diet",
        ],
        "action_query": "eating healthy food",
        "fallback_queries": [
            "healthy meal",
            "eating vegetables",
            "preparing food",
            "family dinner table",
        ],
    },
    "hospital": {
        "english_keywords": [
            "doctor", "hospital", "clinic", "patient", "nurse", "checkup",
        ],
        "action_query": "doctor patient consultation",
        "fallback_queries": [
            "hospital checkup",
            "doctor consultation",
            "medical appointment",
            "patient examination",
        ],
    },
    "lifestyle": {
        "english_keywords": ["routine", "lifestyle", "habit", "morning", "wellness"],
        "action_query": "daily lifestyle routine",
        "fallback_queries": [
            "healthy lifestyle",
            "morning routine",
            "daily habit",
            "wellness routine",
        ],
    },
    "nature": {
        "english_keywords": ["nature", "scenery", "outdoor", "park", "garden", "landscape"],
        "action_query": "nature scenery",
        "fallback_queries": [
            "peaceful nature",
            "outdoor scenery",
            "natural landscape",
            "morning nature walk",
        ],
    },
}


def _matched_category(image_prompt: str):
    """
    Sprint102-2 - image_prompt를 카테고리 키워드와 비교하기 전에
    style_boilerplate_stripper.strip_style_boilerplate()로 스타일/화질/
    조명 상투어를 먼저 제거한다("Semantic Prompt"). 이 순서가 핵심이다
    - 순서를 바꿔 원본 image_prompt를 그대로 토큰화하면, 모든 scene에
    공통으로 붙는 스타일 접미사의 단어(morning/wellness 등)가 실제
    내용과 무관하게 매번 매칭돼버린다(2026-07-14 Production QA 실측).
    """

    semantic_prompt = strip_style_boilerplate(image_prompt or "")
    tokens = set(_clean_words(semantic_prompt))

    for template in CATEGORY_QUERY_TEMPLATES.values():
        if tokens & set(template["english_keywords"]):
            return template

    return None


def plan_video_search_queries(narration: str, image_prompt: str) -> list:
    """
    narration/image_prompt를 변경하지 않는 순수 함수. 우선순위 순서
    (Primary -> Action -> Fallback...)의 검색어 리스트를 반환한다.

    Primary는 항상 extract_search_query(image_prompt)다(기존 동작과
    100% 동일한 값 - 하위 호환). image_prompt에 매칭되는 카테고리가
    있으면 그 카테고리의 action_query + fallback_queries를 순서대로
    이어 붙인다. 매칭되는 카테고리가 없으면 Primary 하나만 담긴
    리스트를 반환한다(빈 리스트가 되지 않도록 항상 최소 1개 보장).
    중복된 문자열은 제거한다(순서는 유지).

    narration은 이 함수 시그니처에 남아 있지만(호출부 하위 호환 +
    향후 확장 여지) 카테고리 판정에는 더 이상 쓰이지 않는다 -
    Sprint102-1 참고.
    """

    primary = extract_search_query(image_prompt)

    queries = [primary]

    template = _matched_category(image_prompt or "")

    if template is not None:
        queries.append(template["action_query"])
        queries.extend(template["fallback_queries"])

    seen = set()
    deduped = []
    for query in queries:
        if query not in seen:
            seen.add(query)
            deduped.append(query)

    return deduped
