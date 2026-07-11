"""
Sprint77 - Asset Planner v1.

지금까지 step02_assets.collect_assets()가 scene 배치를 처리하기
직전에 두 군데(select_ai_priority_scenes/assign_visual_profiles)에서
따로 계산하던 "이 scene은 AI를 우선할지" + "이 scene의 카메라/구도
Profile"을 하나의 이름 있는 구조(SceneAssetStrategy)로 모은다. 새
판단 로직을 추가하는 게 아니라, 흩어져 있던 배치 단위 사전 계획을
Planner라는 하나의 계층으로 묶어 이후 확장(AI/Stock 균형 고도화,
중복 회피 등)의 기반을 만드는 것이 v1의 범위다.
"""

from typing import Dict

from pydantic import BaseModel


class VisualProfile(BaseModel):
    camera_distance: str
    camera_angle: str
    composition: str
    lighting: str


class SceneAssetStrategy(BaseModel):
    scene: int
    prefer_ai: bool
    visual_profile: VisualProfile
    # Sprint78 - Asset Planner v2 (Diversity Planner). 이 scene이
    # 영상 전체에서 맡는 시각적 역할(hero/detail/transition/context).
    # asset_planner.assign_scene_roles()가 배정한다.
    scene_role: str
    # Sprint79 - Asset Planner v3 (Shot Type Planner). 이 scene의 촬영
    # shot scale(wide/medium/close_up/overhead). visual_profile.
    # composition(구도 스타일)과는 다른 축이라 필드명을 분리했다.
    # asset_planner.assign_scene_shots()가 배정한다.
    scene_shot: str


class AssetPlan(BaseModel):
    strategies: Dict[int, SceneAssetStrategy]
