"""
Sprint38 - Hybrid Asset Engine.

Scene의 narration/image_prompt를 키워드로 훑어 "AI Image가 우선되어야
하는 scene"인지 판단합니다. Gemini 등 AI 호출 없이 규칙 기반으로만
동작하는 순수 함수들이라 결정적이고 테스트가 쉽습니다.

주의: 이 모듈은 "검색을 생략할지"를 정하지 않습니다 - AI 우선 scene도
asset_integration_service.py에서 Pexels/Pixabay 검색을 그대로 수행하고,
검색된 후보의 품질 점수가 ASSET_MODE의 pexels_quality_threshold를
넘으면 그대로 Pexels를 채택합니다(비용보다 품질 우선). 이 모듈은 단지
"어떤 scene을 그 품질 게이트 대상으로 삼을지"만 배치 단위로 정합니다.
"""

import re

# 인체 내부/의료 설명 정확도가 중요한 scene - 스톡 사진이 실제로 관련
# 있을 가능성이 낮거나(장기/세포/혈관 등은 정확한 스톡 사진을 찾기
# 어려움), 정확도가 중요해서 AI로 정밀하게 생성하는 편이 나은 주제들.
#
# Sprint38 1차 구현에는 "person"/"people"/"man"/"woman"이 있었으나,
# 이 파이프라인의 모든 scene image_prompt가 항상 "Korean woman/man"
# 형태로 인물을 묘사하므로(Sprint34 Visual Consistency Engine) 이
# 키워드들은 의료/비의료를 전혀 구분하지 못하고 모든 scene에 동일하게
# 잡음만 더했다 - 실측(2026-07-06 E2E)으로 확인되어 제거했다.
AI_PRIORITY_KEYWORDS = {
    "사람", "의사", "병원", "장기", "혈관", "세포", "질병", "설명도", "해부학",
    "doctor", "physician", "patient", "hospital", "clinic", "clinical",
    "surgery", "organ", "organs", "blood vessel", "vessel", "artery",
    "vein", "blood", "cell", "cells", "disease", "diagram", "anatomy",
    "anatomical", "medical", "torso", "stomach", "liver", "kidney",
    "heart", "brain", "lung", "lungs", "intestine", "intestines", "colon",
    "pancreas", "muscle", "muscles", "bone", "bones", "skeleton",
    "digestive", "digestion", "xray", "x-ray", "mri", "ct scan", "ct",
    "ultrasound", "endoscopy", "microscope", "laboratory",
}

# 풍경/생활/음식처럼 스톡 사진으로 충분히 대체 가능한 주제들 - 이런
# scene은 기본적으로 Pexels 우선이며 AI 우선 후보에서 제외한다.
PEXELS_PRIORITY_KEYWORDS = {
    "풍경", "숲", "바다", "물", "운동", "산책", "과일", "채소", "음식", "생활", "배경",
    "landscape", "scenery", "forest", "sea", "ocean", "water", "exercise",
    "workout", "walk", "walking", "fruit", "vegetable", "food", "lifestyle",
    "background", "nature", "kitchen", "home", "morning",
}


def _matches(keyword_lower: str, text_lower: str) -> bool:
    """
    ASCII(영어) 키워드는 정규식 \\b 단어 경계로 감싸 정확히 단어(또는
    구) 단위로만 매칭한다 - 단순 부분 문자열 포함(in)을 쓰면 "man"이
    "human"/"woman" 안에서도 매칭되는 등 엉뚱한 오탐이 생기기
    때문이다(2026-07-06 실측으로 확인).

    한글 키워드는 \\b를 쓰지 않고 기존처럼 부분 문자열 포함으로
    판단한다 - 한국어는 명사에 조사가 공백 없이 바로 붙으므로("사람" +
    "이" -> "사람이") \\b 경계를 적용하면 조사가 붙은 거의 모든 문장에서
    매칭이 실패해버린다(예: "사람이 숲에서"에서 "사람"이 안 잡힘).
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


def classify_scene_importance(scene: dict) -> dict:
    """
    scene 하나의 narration + image_prompt를 합쳐 키워드 매칭 개수를
    계산합니다. 순수 함수입니다.

    반환값: {"ai_score": int, "pexels_score": int, "prefers_ai": bool}
    ai_score가 pexels_score보다 확실히 클 때만 prefers_ai=True입니다 -
    동점이거나 애매하면 기본값인 Pexels 우선으로 남겨(비용 절감 기본
    목표), AI 우선은 명확한 신호가 있을 때만 켠다.
    """

    text = f"{scene.get('narration', '')} {scene.get('image_prompt', '')}"

    ai_score = _count_matches(text, AI_PRIORITY_KEYWORDS)
    pexels_score = _count_matches(text, PEXELS_PRIORITY_KEYWORDS)

    return {
        "ai_score": ai_score,
        "pexels_score": pexels_score,
        "prefers_ai": ai_score > pexels_score,
    }


MEDICAL_STRICTNESS_STEP = 0.02
MAX_EFFECTIVE_THRESHOLD = 0.99


def effective_pexels_threshold(scene: dict, base_threshold: float) -> float:
    """
    asset_quality_scorer.score_asset()은 세로 비율(portrait) 일치
    여부만 relevance 신호로 쓰기 때문에(Sprint28의 알려진 한계),
    portrait인 Pexels 후보는 사실상 항상 base_threshold를 넘겨버려
    "품질 게이트"가 사실상 무력화되는 문제가 있었다(2026-07-06 실측 -
    portrait pexels_image가 항상 0.92를 받아 balanced 임계값 0.90을
    통과).

    이를 보완하기 위해, classify_scene_importance()가 이미 계산한
    텍스트 기반 의료 관련성 신호(ai_score - pexels_score)를 재사용해
    "이 scene이 의료적으로 명확할수록 Pexels를 더 까다롭게 걸러낸다"는
    보정을 더한다 - 실제 이미지 내용을 분석하는 건 아니지만(Vision AI
    호출은 비용 절감이라는 Sprint38 목표와 상충), 이미 갖고 있는
    텍스트 신호만으로 orientation 단일 신호보다는 나은 근사치를 만든다.

    net_medical_signal이 클수록(뚜렷하게 의료적일수록) 임계값이 올라가
    portrait 매칭 정도로는 통과하기 어려워지고, 결과적으로 AI Image가
    선택될 가능성이 커진다. MAX_EFFECTIVE_THRESHOLD로 상한을 둬 임계값이
    1.0을 넘어 "항상 AI"로 고정돼버리는 극단은 피한다.
    """

    result = classify_scene_importance(scene)
    net_medical_signal = max(0, result["ai_score"] - result["pexels_score"])

    return min(
        base_threshold + net_medical_signal * MEDICAL_STRICTNESS_STEP,
        MAX_EFFECTIVE_THRESHOLD,
    )


def select_ai_priority_scenes(scenes: list, ai_ratio_cap: float) -> set:
    """
    scene 목록 전체를 대상으로, ai_ratio_cap(0~1) 이내에서만 AI 우선
    처리 대상 scene 번호를 골라 집합으로 반환합니다. 순수 함수입니다.

    ai_ratio_cap은 강제로 채워야 하는 목표치가 아니라 상한이다 -
    "AI 우선"으로 분류된(prefers_ai=True) scene이 상한보다 적으면 있는
    만큼만 선택되고, 더 많으면 ai_score가 가장 높은 scene들만(동점이면
    원래 scene 순서를 유지) 상한 개수까지만 선택된다. 선택된 scene도
    실제로 AI를 쓸지는 이후 asset_integration_service.py의 Pexels
    품질 게이트가 최종 결정한다 - 여기서는 "품질 게이트를 적용할
    후보"만 고른다.
    """

    if not scenes:
        return set()

    target_count = round(len(scenes) * ai_ratio_cap)

    if target_count <= 0:
        return set()

    scored = [
        (scene, classify_scene_importance(scene))
        for scene in scenes
    ]

    prioritized = [
        (scene, result["ai_score"])
        for scene, result in scored
        if result["prefers_ai"]
    ]

    prioritized.sort(key=lambda pair: pair[1], reverse=True)

    return {scene["scene"] for scene, _ in prioritized[:target_count]}
