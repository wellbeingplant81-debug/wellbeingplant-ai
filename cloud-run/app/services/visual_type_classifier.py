"""
Sprint60 - Smart Visual Selection v1.

Scene의 narration + image_prompt를 키워드로 훑어 이 scene에 실사
스톡("real")과 AI 생성("ai") 중 어느 쪽을 먼저 시도할지를 규칙 기반으로
정합니다. LLM 호출 없이 결정적으로 동작하는 순수 함수들입니다.

asset_priority_classifier.py(Sprint38)의 prefers_ai/ai_ratio_cap과는
목적이 다릅니다 - 그쪽은 "품질 게이트를 적용할 배치 상한"을 정하는
소프트 메커니즘이고, 이 모듈은 scene마다 "real"/"ai" 둘 중 하나를 못박아
image 선택 순서를 하드 분기시키는 Sprint60 전용 v1 메커니즘입니다. 두
모듈은 서로 호출하지 않고 완전히 독립적으로 유지합니다.
"""

import re

VISUAL_TYPE_REAL = "real"
VISUAL_TYPE_AI = "ai"

# 스톡 사진으로 정확히 표현하기 어려운 주제(인체 내부/미생물/생화학
# 등) - Imagen으로 먼저 시도한다.
AI_VISUAL_KEYWORDS = {
    "혈관", "세포", "장내세균", "유익균", "유해균", "콜레스테롤",
    "미토콘드리아", "염증", "신경세포", "암세포", "호르몬", "인슐린",
    "박테리아", "세균", "유전자",
    "dna", "blood vessel", "blood vessels", "cell", "cells",
    "gut bacteria", "gut flora", "probiotics", "microbiome",
    "cholesterol", "mitochondria", "inflammation", "neuron", "neurons",
    "nerve cell", "nerve cells", "cancer cell", "cancer cells",
    "hormone", "hormones", "insulin", "bacteria", "artery", "arteries",
    "vein", "veins", "capillary", "capillaries", "antibody", "antibodies",
    "enzyme", "enzymes", "molecule", "molecular", "receptor", "synapse",
    "chromosome",
}

# 스톡 사진으로 충분히 대체 가능한 일상/인물/의료 현장 주제 - Pexels로
# 먼저 시도한다. 기본값(동점 포함)도 이쪽이다(비용 절감).
#
# 주의: "woman"/"man"/"person" 같은 범용 영어 단어는 일부러 넣지 않는다
# - Visual Consistency Engine이 모든 image_prompt에 "Korean woman/man"을
# 항상 끼워 넣으므로, 이런 단어를 넣으면 모든 scene에서 무조건 매칭돼
# real_score를 밀어올려 진짜 ai 신호를 덮어버린다(asset_priority_
# classifier.py에 2026-07-06 실측으로 이미 기록된 것과 동일한 함정).
REAL_VISUAL_KEYWORDS = {
    "사람", "병원", "운동", "산책", "식사", "과일", "채소", "의사",
    "간호사", "요가", "스트레칭", "수면", "물 마시는", "마시는 물",
    "물 한 잔", "물",
    "hospital", "doctor", "physician", "nurse", "exercise", "workout",
    "walk", "walking", "meal", "eating", "fruit", "vegetable",
    "drinking water", "water", "yoga", "stretching", "sleep", "kitchen",
    "morning",
}


def _matches(keyword_lower: str, text_lower: str) -> bool:
    """
    ASCII 키워드는 \\b 단어 경계로 정확히 매칭하고(부분 문자열 오탐
    방지, 예: "cell"이 "cellular" 안에서 매칭되지 않도록), 한글
    키워드는 조사가 붙는 한국어 특성상 부분 문자열 포함으로 매칭한다.
    asset_priority_classifier._matches()와 동일한 방식이다.
    """

    if keyword_lower.isascii():
        pattern = r"\b" + re.escape(keyword_lower) + r"\b"
        return bool(re.search(pattern, text_lower))

    return keyword_lower in text_lower


def _count_matches(text: str, keywords: set) -> int:

    text_lower = text.lower()

    return sum(
        1
        for keyword in keywords
        if _matches(keyword.lower(), text_lower)
    )


def determine_visual_type(scene: dict) -> str:
    """
    scene 하나의 narration + image_prompt를 합쳐 AI_VISUAL_KEYWORDS /
    REAL_VISUAL_KEYWORDS 매칭 개수를 비교합니다. ai 매칭이 real 매칭보다
    확실히 많을 때만 "ai"를 반환하고, 그 외(동점 포함, 아무 키워드도
    없는 경우 포함)는 "real"을 반환합니다 - 애매하면 비용이 저렴한
    Pexels 우선 쪽으로 기본값을 둡니다. 순수 함수입니다.
    """

    text = f"{scene.get('narration', '')} {scene.get('image_prompt', '')}"

    ai_score = _count_matches(text, AI_VISUAL_KEYWORDS)
    real_score = _count_matches(text, REAL_VISUAL_KEYWORDS)

    return VISUAL_TYPE_AI if ai_score > real_score else VISUAL_TYPE_REAL


def apply_visual_type(scenes: list) -> list:
    """
    scenes 각각에 determine_visual_type() 결과를 "visual_type" 필드로
    채운 새 scene dict 리스트를 반환합니다. 입력 scenes/scene dict는
    변경하지 않습니다(다른 apply_*류 함수들과 동일한 불변 계약).
    """

    enriched = []

    for scene in scenes or []:

        new_scene = dict(scene)
        new_scene["visual_type"] = determine_visual_type(scene)
        enriched.append(new_scene)

    return enriched
