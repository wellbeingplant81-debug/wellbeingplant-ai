"""
Sprint47 - Prompt Effectiveness Engine.

Sprint46 prompt_enrichment_service가 만든 enriched_prompt가 실제로
얼마나 "좋은" 프롬프트인지 규칙 기반으로 채점합니다. asset_quality_service
(Sprint43)와 동일한 스타일 - 0~100점, 항목별 배점, PASS_THRESHOLD -
을 따르는 순수 측정 전용 모듈입니다. 이 모듈은 절대 프롬프트나 scene을
수정하지 않습니다 - 점수만 계산합니다.
"""

import re

from app.services import prompt_enrichment_service
from app.services import scene_planner_service

# 각 검사 항목이 통과했을 때 더해지는 점수 (합계 100).
POINTS = {
    "prompt_preserved": 25,
    "camera": 15,
    "visual_type": 15,
    "purpose": 15,
    "length": 15,
    "keywords": 10,
    "duplicate_free": 5,
}

PASS_THRESHOLD = 80

MIN_PROMPT_LENGTH = 10
MAX_PROMPT_LENGTH = 400
MIN_KEYWORD_COUNT = 1


def _check_prompt_preserved(original_prompt: str, enriched_prompt: str) -> bool:
    """원본이 비어 있으면 지켜야 할 것이 없으므로 통과로 처리합니다."""

    if not original_prompt:
        return True

    return original_prompt in (enriched_prompt or "")


def _check_descriptor_reflected(
    enriched_prompt: str,
    scene_plan_item: dict,
    field: str,
    phrase_map: dict,
) -> bool:
    """
    scene_plan_item에 해당 field가 아예 없거나(Planner 비활성) 알려지지
    않은 값이면 "확인할 대상이 없다"는 뜻이므로 통과로 처리합니다 -
    prompt_enrichment_service.enrich_prompt()가 같은 이유로 원본을
    그대로 반환하는 것과 대칭되는 규칙입니다.

    Sprint69 (Scene Planner v2) - 그 값이 프롬프트에서 읽어 온 것이면
    이미 반영되어 있는 것이므로 통과입니다. 이 검사가 보려는 것은
    "계획한 연출이 프롬프트에 담겼는가"인데, 프롬프트가 출처라면 담기고
    말고 할 것이 없습니다.

    문자열로 다시 찾지 않는 이유가 중요합니다. 프롬프트는 같은 뜻을
    다른 말로 적을 수 있습니다 - "macro"는 close_up으로 읽히지만
    "close-up"이라는 글자는 없습니다. 여기서 글자를 찾으면 프롬프트를
    존중했다는 이유로 오히려 감점되어, 점수가 실제 품질과 반대로
    움직입니다.
    """

    scene_plan_item = scene_plan_item or {}

    value = scene_plan_item.get(field)
    phrase = phrase_map.get(value)

    if not phrase:
        return True

    if scene_plan_item.get(f"{field}_source") == scene_planner_service.PROMPT_SOURCE:
        return True

    return phrase in (enriched_prompt or "")


def _check_length(enriched_prompt: str) -> bool:
    length = len(enriched_prompt or "")
    return MIN_PROMPT_LENGTH <= length <= MAX_PROMPT_LENGTH


def _check_keywords(scene_plan_item: dict) -> bool:
    keywords = (scene_plan_item or {}).get("keywords") or []
    return len(keywords) >= MIN_KEYWORD_COUNT


def _check_no_duplicate_sentences(enriched_prompt: str) -> bool:
    """
    쉼표/마침표 기준으로 문장/구를 나눠, 대소문자 무시 완전 일치
    중복이 있는지 확인합니다. Enrichment가 이미 있는 문구를 중복
    추가하는 회귀(예: 동일 scene을 두 번 enrich)를 잡기 위함입니다.
    """

    if not enriched_prompt:
        return True

    fragments = [
        fragment.strip().lower()
        for fragment in re.split(r"[.,]", enriched_prompt)
        if fragment.strip()
    ]

    return len(fragments) == len(set(fragments))


def evaluate_prompt(
    original_prompt: str,
    enriched_prompt: str,
    scene_plan_item: dict,
) -> dict:
    """
    scene 하나의 (original_prompt, enriched_prompt) 쌍을 0~100점
    규칙 기반으로 채점합니다. 순수 함수입니다 - 파일/네트워크 접근이나
    프롬프트 변경이 전혀 없습니다.

    반환값: {"score": int, "passed": bool, "metrics": {
        "prompt_preserved": bool, "camera": bool, "visual_type": bool,
        "purpose": bool, "length": int, "keywords": int,
        "duplicate_free": bool,
    }}
    """

    scene_plan_item = scene_plan_item or {}

    prompt_preserved = _check_prompt_preserved(original_prompt, enriched_prompt)
    camera_ok = _check_descriptor_reflected(
        enriched_prompt, scene_plan_item, "camera",
        prompt_enrichment_service.CAMERA_PHRASES,
    )
    visual_type_ok = _check_descriptor_reflected(
        enriched_prompt, scene_plan_item, "visual_type",
        prompt_enrichment_service.VISUAL_TYPE_PHRASES,
    )
    purpose_ok = _check_descriptor_reflected(
        enriched_prompt, scene_plan_item, "purpose",
        prompt_enrichment_service.PURPOSE_PHRASES,
    )
    length = len(enriched_prompt or "")
    length_ok = _check_length(enriched_prompt)
    keyword_count = len(scene_plan_item.get("keywords") or [])
    keywords_ok = _check_keywords(scene_plan_item)
    duplicate_free = _check_no_duplicate_sentences(enriched_prompt)

    checks = {
        "prompt_preserved": prompt_preserved,
        "camera": camera_ok,
        "visual_type": visual_type_ok,
        "purpose": purpose_ok,
        "length": length_ok,
        "keywords": keywords_ok,
        "duplicate_free": duplicate_free,
    }

    score = sum(POINTS[key] for key, ok in checks.items() if ok)

    return {
        "score": score,
        "passed": score >= PASS_THRESHOLD,
        "metrics": {
            "prompt_preserved": prompt_preserved,
            "camera": camera_ok,
            "visual_type": visual_type_ok,
            "purpose": purpose_ok,
            "length": length,
            "keywords": keyword_count,
            "duplicate_free": duplicate_free,
        },
    }


def evaluate_scenes(
    original_scenes: list,
    enriched_scenes: list,
    scene_plan: list,
) -> list:
    """
    scene 배치 전체에 evaluate_prompt()를 적용하는 pipeline 연동용
    래퍼입니다. scene 번호로 원본/enriched 프롬프트와 scene_plan
    항목을 매칭합니다 (apply_prompt_enrichment()와 동일한 매칭 방식).
    scene이나 프롬프트를 변경하지 않는 순수 함수입니다.

    반환값: [{"scene_id": int, "score": int, "passed": bool,
              "metrics": {...}}, ...] - enriched_scenes 순서를 그대로
    유지합니다.
    """

    plan_by_scene_id = {
        item["scene_id"]: item for item in (scene_plan or [])
    }
    original_by_scene = {
        scene.get("scene"): scene for scene in (original_scenes or [])
    }

    results = []

    for scene in (enriched_scenes or []):

        scene_number = scene.get("scene")
        original = original_by_scene.get(scene_number, {})

        result = evaluate_prompt(
            original.get("image_prompt", ""),
            scene.get("image_prompt", ""),
            plan_by_scene_id.get(scene_number),
        )

        results.append({"scene_id": scene_number, **result})

    return results
