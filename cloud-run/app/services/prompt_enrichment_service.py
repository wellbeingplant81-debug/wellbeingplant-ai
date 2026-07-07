"""
Sprint46 - Prompt Enrichment Engine.

Sprint44/45의 scene_planner_service.plan_scenes() 결과(scene_plan)를
image_prompt에 선택적으로 반영합니다. 항상 기존 image_prompt를
그대로 유지한 채 뒤에 설명 문구만 덧붙이는 append-only 방식입니다 -
절대 원본 프롬프트를 삭제하거나 대체하지 않습니다.
"""

from app.services import scene_planner_service

CAMERA_PHRASES = {
    scene_planner_service.HOOK_CAMERA: "close-up",
    scene_planner_service.CTA_CAMERA: "medium shot",
    scene_planner_service.DEVELOPMENT_CAMERA: "wide shot",
}

VISUAL_TYPE_PHRASES = {
    scene_planner_service.PHOTO_REALISTIC_VISUAL_TYPE: "photo realistic",
    scene_planner_service.ILLUSTRATIVE_VISUAL_TYPE: "illustrative",
    "cinematic": "cinematic",
}

PURPOSE_PHRASES = {
    scene_planner_service.HOOK_PURPOSE: "hook",
    scene_planner_service.DEVELOPMENT_PURPOSE: "development",
    scene_planner_service.CTA_PURPOSE: "cta",
}


def enrich_prompt(original_prompt: str, scene_plan_item: dict) -> str:
    """
    scene_plan_item(scene_planner_service.plan_scenes()의 항목 하나)의
    camera/visual_type/purpose를 사람이 읽을 수 있는 문구로 바꿔
    original_prompt 뒤에 덧붙입니다. 순수 함수입니다.

    scene_plan_item이 없거나(Planner 비활성/미매칭) 알려진 설명 문구가
    하나도 없으면 original_prompt를 그대로 반환합니다 - Sprint45
    "Planner가 비활성화되어도 기존 결과와 동일해야 함" 원칙을
    이 함수 레벨에서도 그대로 지킵니다.
    """

    if not scene_plan_item:
        return original_prompt

    descriptors = [
        phrase
        for phrase in (
            CAMERA_PHRASES.get(scene_plan_item.get("camera")),
            VISUAL_TYPE_PHRASES.get(scene_plan_item.get("visual_type")),
            PURPOSE_PHRASES.get(scene_plan_item.get("purpose")),
        )
        if phrase
    ]

    if not descriptors:
        return original_prompt

    suffix = ", ".join(descriptors)

    return f"{original_prompt}, {suffix}" if original_prompt else suffix


def apply_prompt_enrichment(scenes: list, scene_plan: list) -> list:
    """
    scene_plan을 scene_id <-> scene 번호로 매칭해 각 scene의
    image_prompt를 enrich_prompt()로 보강한 새 scene 리스트를
    반환합니다. 입력 scenes/scene_plan은 변경하지 않고, 순서도 절대
    바꾸지 않습니다 (transition_engine/visual_consistency_engine과
    동일한 overlay 방식). 매칭되는 scene_plan 항목이 없는 scene은
    image_prompt를 그대로 유지합니다.
    """

    plan_by_scene_id = {item["scene_id"]: item for item in (scene_plan or [])}

    return [
        {
            **scene,
            "image_prompt": enrich_prompt(
                scene.get("image_prompt", ""),
                plan_by_scene_id.get(scene.get("scene")),
            ),
        }
        for scene in scenes
    ]
