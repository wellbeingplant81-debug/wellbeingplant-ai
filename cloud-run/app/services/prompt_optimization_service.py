"""
Sprint48 - Adaptive Prompt Optimization Engine.

Sprint47 prompt_effectiveness_service.evaluate_prompt()의 결과
(prompt_metrics)를 읽어, 실패한 항목만 최소한으로 고칩니다. 항상
original_prompt를 그대로 보존하고(삭제/재작성 없음), Sprint46
prompt_enrichment_service와 동일한 phrase map/append 방식만 재사용해
"이미 실패로 판정난 것"만 좁게 수정합니다 - 공격적인 프롬프트
재작성은 절대 하지 않습니다.
"""

from app.services import prompt_effectiveness_service
from app.services import prompt_enrichment_service

MAX_PROMPT_LENGTH = prompt_effectiveness_service.MAX_PROMPT_LENGTH


def _append_if_missing(text: str, phrase: str) -> str:

    if not phrase or phrase in text:
        return text

    return f"{text}, {phrase}" if text else phrase


def _dedupe_fragments(text: str) -> str:
    """
    enrich_prompt()이 항상 ", "로 문구를 이어붙이므로, 같은 구분자로
    나눠 대소문자 무시 완전 일치 중복만 제거합니다. 최초 등장한
    순서/표기는 그대로 유지합니다.
    """

    if not text:
        return text

    seen = set()
    deduped = []

    for fragment in text.split(", "):
        key = fragment.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fragment)

    return ", ".join(deduped)


def _trim_to_max_length(text: str, min_length: int) -> str:
    """
    min_length(원본 프롬프트 길이) 밑으로는 절대 자르지 않습니다 -
    원본이 이미 MAX_PROMPT_LENGTH보다 길면 다듬기를 포기하고 원본을
    그대로 보존하는 쪽을 택합니다(길이 규칙보다 "원본 보존" 원칙 우선).
    쉼표/공백 경계에서 잘라 단어가 중간에 끊기지 않게 합니다.
    """

    limit = max(MAX_PROMPT_LENGTH, min_length)

    if len(text) <= limit:
        return text

    truncated = text[:limit]
    boundary = max(truncated.rfind(","), truncated.rfind(" "))

    if boundary > min_length:
        truncated = truncated[:boundary]

    return truncated.rstrip().rstrip(",").rstrip()


def optimize_prompt(
    original_prompt: str,
    enriched_prompt: str,
    evaluation: dict,
    scene_plan_item: dict,
) -> str:
    """
    evaluation(prompt_effectiveness_service.evaluate_prompt()의 결과)이
    이미 통과(passed=True)했거나 metrics가 없으면(Effectiveness
    비활성/미평가) enriched_prompt를 그대로 반환합니다 - "실패한 항목만
    최소로 고친다"는 원칙에 따라, 평가 정보가 없으면 아무것도 건드리지
    않습니다.

    순수 함수입니다 - evaluation/scene_plan_item을 변경하지 않습니다.
    """

    if not enriched_prompt:
        return enriched_prompt

    if evaluation and evaluation.get("passed"):
        return enriched_prompt

    metrics = (evaluation or {}).get("metrics") or {}
    scene_plan_item = scene_plan_item or {}
    optimized = enriched_prompt

    if (
        metrics.get("prompt_preserved") is False
        and original_prompt
        and original_prompt not in optimized
    ):
        optimized = f"{original_prompt}, {optimized}" if optimized else original_prompt

    if metrics.get("duplicate_free") is False:
        optimized = _dedupe_fragments(optimized)

    if metrics.get("camera") is False:
        phrase = prompt_enrichment_service.CAMERA_PHRASES.get(scene_plan_item.get("camera"))
        optimized = _append_if_missing(optimized, phrase)

    if metrics.get("visual_type") is False:
        phrase = prompt_enrichment_service.VISUAL_TYPE_PHRASES.get(scene_plan_item.get("visual_type"))
        optimized = _append_if_missing(optimized, phrase)

    if metrics.get("purpose") is False:
        phrase = prompt_enrichment_service.PURPOSE_PHRASES.get(scene_plan_item.get("purpose"))
        optimized = _append_if_missing(optimized, phrase)

    if (metrics.get("length") or 0) > MAX_PROMPT_LENGTH:
        optimized = _trim_to_max_length(optimized, len(original_prompt or ""))

    return optimized


def optimize_scenes(
    original_scenes: list,
    enriched_scenes: list,
    prompt_metrics: list,
    scene_plan: list,
) -> list:
    """
    scene 배치 전체에 optimize_prompt()를 적용하는 pipeline 연동용
    래퍼입니다. scene 번호로 원본 프롬프트/prompt_metrics/scene_plan을
    매칭합니다 (evaluate_scenes(), apply_prompt_enrichment()와 동일한
    매칭 방식).

    image_prompt만 바꾸고 나머지 필드(narration, provider 등)는 그대로
    유지하며, scene 순서도 절대 바꾸지 않는 순수 함수입니다.
    """

    original_by_scene = {
        scene.get("scene"): scene for scene in (original_scenes or [])
    }
    metrics_by_scene = {
        entry["scene_id"]: entry for entry in (prompt_metrics or [])
    }
    plan_by_scene = {
        item["scene_id"]: item for item in (scene_plan or [])
    }

    result = []

    for scene in (enriched_scenes or []):

        scene_number = scene.get("scene")
        original = original_by_scene.get(scene_number, {})

        optimized_prompt = optimize_prompt(
            original.get("image_prompt", ""),
            scene.get("image_prompt", ""),
            metrics_by_scene.get(scene_number),
            plan_by_scene.get(scene_number),
        )

        result.append({**scene, "image_prompt": optimized_prompt})

    return result
