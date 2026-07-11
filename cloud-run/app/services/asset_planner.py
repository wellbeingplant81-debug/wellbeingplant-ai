"""
Sprint77 - Asset Planner v1.

step02_assets.collect_assets()가 scene 배치를 병렬 처리하기 직전에
따로 계산하던 두 가지 배치 단위 사전 계획 -
- asset_priority_classifier.select_ai_priority_scenes() (AI/Stock 균형)
- visual_diversity_engine.assign_visual_profiles() (Visual Diversity,
  이미 배정된 조합을 피하는 방식으로 중복도 줄인다)
을 SceneAssetStrategy 하나로 묶어 반환한다. 새 판단 로직은 추가하지
않는다 - 기존 두 함수를 그대로 재사용해 결과를 합치기만 한다. 이렇게
하나의 이름 있는 계층으로 모아두는 것 자체가 이후 Planner 확장(더
정교한 AI/Stock 균형, 사전 중복 회피 등)의 기반이 된다.

반환값은 pydantic 모델이 아니라 순수 dict다 - pipeline.py가
data["asset_plan"]에 그대로 담아 json.dump()로 script.json에 저장하기
때문이다(app/models/asset_plan.py의 SceneAssetStrategy로 형태만
검증한 뒤 model_dump()한다).

Sprint78 - Asset Planner v2 (Diversity Planner). assign_scene_roles()는
scene 배치 전체를 대상으로 "이 scene이 영상에서 맡는 시각적 역할"
(hero/detail/transition/context)을 배정하는 순수 함수다. 이미 존재하는
asset_integration_service.ASSET_ROLES(environment/subject/detail/
transition)는 "같은 scene 안 4개 AI asset끼리의" 역할이라 - 이 함수가
다루는 "scene 하나 전체의" 역할과는 다른 축이며 서로 관여하지 않는다.
"""

from app.models.asset_plan import SceneAssetStrategy
from app.services.asset_mode_config import get_ai_ratio_cap
from app.services.asset_priority_classifier import select_ai_priority_scenes
from app.services.visual_diversity_engine import assign_visual_profiles


SCENE_VISUAL_ROLES = ["hero", "detail", "transition", "context"]

# Scene 1(hero, 아래 assign_scene_roles 참고)을 제외한 나머지 scene이
# 순환하는 순서. hero는 항상 첫 scene 전용이라 이 목록에서 뺐다.
_CYCLE_SCENE_VISUAL_ROLES = ["detail", "transition", "context"]


def assign_scene_roles(scenes: list) -> dict:
    """
    scene 목록을 받아 {scene_number: role} 딕셔너리를 반환한다. 순수
    함수다 - 랜덤을 쓰지 않고, 입력 scenes를 변경하지 않으며, 같은
    입력에는 항상 같은 결과를 낸다.

    첫 scene은 항상 "hero"(파이프라인 전반에서 이미 hook/커버 scene
    으로 특별 취급되는 관례와 동일선상). 이후 scene은 "detail" ->
    "transition" -> "context" 순으로 순환 배정되어, 연속된 scene이
    같은 role을 반복하지 않는다.
    """

    if not scenes:
        return {}

    roles = {}

    for index, scene in enumerate(scenes):
        scene_number = scene["scene"]

        if index == 0:
            roles[scene_number] = "hero"
        else:
            roles[scene_number] = _CYCLE_SCENE_VISUAL_ROLES[
                (index - 1) % len(_CYCLE_SCENE_VISUAL_ROLES)
            ]

    return roles


def plan_asset_strategy(scenes: list) -> dict:

    if not scenes:
        return {}

    ai_priority_scenes = select_ai_priority_scenes(scenes, get_ai_ratio_cap())
    visual_profiles = assign_visual_profiles(scenes)
    scene_roles = assign_scene_roles(scenes)

    plan = {}

    for scene in scenes:
        scene_number = scene["scene"]

        strategy = SceneAssetStrategy(
            scene=scene_number,
            prefer_ai=scene_number in ai_priority_scenes,
            visual_profile=visual_profiles[scene_number],
            scene_role=scene_roles[scene_number],
        )

        plan[scene_number] = strategy.model_dump()

    return plan
