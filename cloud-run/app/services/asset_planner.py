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
"""

from app.models.asset_plan import SceneAssetStrategy
from app.services.asset_mode_config import get_ai_ratio_cap
from app.services.asset_priority_classifier import select_ai_priority_scenes
from app.services.visual_diversity_engine import assign_visual_profiles


def plan_asset_strategy(scenes: list) -> dict:

    if not scenes:
        return {}

    ai_priority_scenes = select_ai_priority_scenes(scenes, get_ai_ratio_cap())
    visual_profiles = assign_visual_profiles(scenes)

    plan = {}

    for scene in scenes:
        scene_number = scene["scene"]

        strategy = SceneAssetStrategy(
            scene=scene_number,
            prefer_ai=scene_number in ai_priority_scenes,
            visual_profile=visual_profiles[scene_number],
        )

        plan[scene_number] = strategy.model_dump()

    return plan
