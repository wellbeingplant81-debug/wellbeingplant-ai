import json
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_planner import (
    SCENE_SHOT_TYPES,
    SCENE_VISUAL_ROLES,
    assign_scene_roles,
    assign_scene_shots,
    plan_asset_strategy,
)
from app.services.asset_priority_classifier import select_ai_priority_scenes
from app.services.asset_mode_config import get_ai_ratio_cap
from app.services.visual_diversity_engine import assign_visual_profiles


SAMPLE_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2"},
    {"scene": 3, "narration": "n3", "image_prompt": "p3"},
]

MEDICAL_SCENES = [
    {
        "scene": 1,
        "narration": "혈관과 세포 이야기",
        "image_prompt": "diagram of blood vessel anatomy",
    },
    {"scene": 2, "narration": "n2", "image_prompt": "p2"},
    {"scene": 3, "narration": "n3", "image_prompt": "p3"},
]

# 실제 파이프라인의 전형적인 scene 개수(script_prompt.py "정확히 6개")와
# 맞춘 fixture - role 다양성/반복 회피를 의미 있게 검증하려면 최소
# SCENE_VISUAL_ROLES 개수보다 많은 scene이 필요하다.
SIX_SCENES = [
    {"scene": i, "narration": f"n{i}", "image_prompt": f"p{i}"}
    for i in range(1, 7)
]


class TestPlanAssetStrategy(unittest.TestCase):

    def test_empty_scenes_returns_empty_plan(self):
        self.assertEqual(plan_asset_strategy([]), {})

    def test_returns_dict_keyed_by_scene_number(self):
        plan = plan_asset_strategy(SAMPLE_SCENES)

        self.assertEqual(set(plan.keys()), {1, 2, 3})

    def test_each_entry_has_scene_prefer_ai_and_visual_profile(self):
        plan = plan_asset_strategy(SAMPLE_SCENES)

        for scene_number, strategy in plan.items():
            self.assertEqual(strategy["scene"], scene_number)
            self.assertIn("prefer_ai", strategy)
            self.assertIn("visual_profile", strategy)
            self.assertIn("camera_distance", strategy["visual_profile"])
            self.assertIn("camera_angle", strategy["visual_profile"])
            self.assertIn("composition", strategy["visual_profile"])
            self.assertIn("lighting", strategy["visual_profile"])

    def test_prefer_ai_matches_existing_asset_priority_classifier(self):
        # Sprint77 - Planner는 새 판단 로직을 추가하지 않고 기존
        # select_ai_priority_scenes()를 그대로 재사용한다.
        plan = plan_asset_strategy(MEDICAL_SCENES)

        expected_ai_scenes = select_ai_priority_scenes(
            MEDICAL_SCENES, get_ai_ratio_cap(),
        )

        for scene_number, strategy in plan.items():
            self.assertEqual(
                strategy["prefer_ai"], scene_number in expected_ai_scenes,
            )

    def test_visual_profile_matches_existing_visual_diversity_engine(self):
        # Sprint77 - Planner는 새 판단 로직을 추가하지 않고 기존
        # assign_visual_profiles()를 그대로 재사용한다.
        plan = plan_asset_strategy(SAMPLE_SCENES)

        expected_profiles = assign_visual_profiles(SAMPLE_SCENES)

        for scene_number, strategy in plan.items():
            self.assertEqual(
                strategy["visual_profile"], expected_profiles[scene_number],
            )

    def test_result_is_plain_json_serializable(self):
        plan = plan_asset_strategy(SAMPLE_SCENES)

        # pipeline.py가 data["asset_plan"]에 그대로 담아 json.dump()로
        # script.json에 저장하므로, pydantic 객체가 아니라 순수 dict여야 한다.
        json.dumps(plan)

    def test_does_not_mutate_input_scenes(self):
        scenes_copy = [dict(s) for s in SAMPLE_SCENES]

        plan_asset_strategy(SAMPLE_SCENES)

        self.assertEqual(SAMPLE_SCENES, scenes_copy)


# --- Sprint78: Asset Planner v2 (Diversity Planner) - scene visual role ---


class TestAssignSceneRoles(unittest.TestCase):
    """
    Sprint78 - scene 배치 전체를 대상으로 "이 scene이 영상에서 맡는
    시각적 역할"(hero/detail/transition/context)을 배정한다. 이미
    존재하는 asset_integration_service.ASSET_ROLES(environment/subject/
    detail/transition)는 "같은 scene 안 4개 AI asset끼리의" 역할이라
    - 이 테스트가 다루는 "scene 하나 전체의" 역할과는 다른 축이다.
    """

    def test_empty_scenes_returns_empty_dict(self):
        self.assertEqual(assign_scene_roles([]), {})

    def test_returns_role_for_every_scene(self):
        roles = assign_scene_roles(SAMPLE_SCENES)

        self.assertEqual(set(roles.keys()), {1, 2, 3})

    def test_all_assigned_roles_are_valid_scene_visual_roles(self):
        roles = assign_scene_roles(SIX_SCENES)

        for role in roles.values():
            self.assertIn(role, SCENE_VISUAL_ROLES)

    def test_roles_are_diverse_not_all_identical(self):
        roles = assign_scene_roles(SIX_SCENES)

        self.assertGreater(len(set(roles.values())), 1)

    def test_same_role_does_not_repeat_consecutively(self):
        roles = assign_scene_roles(SIX_SCENES)

        ordered = [roles[scene["scene"]] for scene in SIX_SCENES]

        for previous, current in zip(ordered, ordered[1:]):
            self.assertNotEqual(previous, current)

    def test_first_scene_is_hero_role(self):
        # Scene 1은 파이프라인 전반에서 이미 "hook/커버" scene으로
        # 특별 취급된다(asset_integration_service.is_hook_scene,
        # script_prompt.py Scene 1 규칙 등과 동일한 관례).
        roles = assign_scene_roles(SIX_SCENES)

        self.assertEqual(roles[1], "hero")

    def test_all_roles_used_at_least_once_when_enough_scenes(self):
        # scene 개수가 SCENE_VISUAL_ROLES 개수 이상이면(6 >= 4) 모든
        # role이 최소 한 번은 쓰여야 "다양하게 분배"라고 볼 수 있다.
        roles = assign_scene_roles(SIX_SCENES)

        self.assertEqual(set(roles.values()), set(SCENE_VISUAL_ROLES))

    def test_does_not_mutate_input_scenes(self):
        scenes_copy = [dict(s) for s in SIX_SCENES]

        assign_scene_roles(SIX_SCENES)

        self.assertEqual(SIX_SCENES, scenes_copy)


class TestPlanAssetStrategyIncludesSceneRole(unittest.TestCase):
    """Sprint78 - plan_asset_strategy()의 결과 dict에 scene_role이
    함께 실려야 한다(기존 scene/prefer_ai/visual_profile 필드에 추가)."""

    def test_plan_includes_scene_role_for_every_scene(self):
        plan = plan_asset_strategy(SIX_SCENES)

        for strategy in plan.values():
            self.assertIn("scene_role", strategy)
            self.assertIn(strategy["scene_role"], SCENE_VISUAL_ROLES)

    def test_plan_scene_role_matches_assign_scene_roles(self):
        plan = plan_asset_strategy(SIX_SCENES)

        expected = assign_scene_roles(SIX_SCENES)

        for scene_number, strategy in plan.items():
            self.assertEqual(strategy["scene_role"], expected[scene_number])

    def test_plan_result_still_json_serializable_with_scene_role(self):
        plan = plan_asset_strategy(SIX_SCENES)

        json.dumps(plan)


# --- Sprint79: Asset Planner v3 (Shot Type Planner) - scene shot type ---


class TestAssignSceneShots(unittest.TestCase):
    """
    Sprint79 - scene 배치 전체를 대상으로 각 scene의 촬영 shot
    scale(SCENE_SHOT_TYPES: wide/medium/close_up/overhead)을 배정한다.
    visual_diversity_engine.assign_visual_profiles()가 만드는
    visual_profile["composition"](centered/rule of thirds/foreground
    framing/leading lines - 구도 "스타일")과는 값 도메인이 다른 별개의
    축이다 - 의미 충돌을 피하기 위해 필드명도 "composition"이 아니라
    "scene_shot"을 쓴다.
    """

    def test_empty_scenes_returns_empty_dict(self):
        self.assertEqual(assign_scene_shots([]), {})

    def test_returns_shot_for_every_scene(self):
        shots = assign_scene_shots(SIX_SCENES)

        self.assertEqual(set(shots.keys()), {1, 2, 3, 4, 5, 6})

    def test_all_assigned_shots_are_valid(self):
        shots = assign_scene_shots(SIX_SCENES)

        for shot in shots.values():
            self.assertIn(shot, SCENE_SHOT_TYPES)

    def test_first_scene_is_wide(self):
        shots = assign_scene_shots(SIX_SCENES)

        self.assertEqual(shots[1], "wide")

    def test_cycles_medium_close_up_overhead_after_first_scene(self):
        shots = assign_scene_shots(SIX_SCENES)

        ordered = [shots[scene["scene"]] for scene in SIX_SCENES]

        self.assertEqual(
            ordered,
            ["wide", "medium", "close_up", "overhead", "medium", "close_up"],
        )

    def test_is_deterministic(self):
        first = assign_scene_shots(SIX_SCENES)
        second = assign_scene_shots(SIX_SCENES)

        self.assertEqual(first, second)

    def test_does_not_mutate_input_scenes(self):
        scenes_copy = [dict(s) for s in SIX_SCENES]

        assign_scene_shots(SIX_SCENES)

        self.assertEqual(SIX_SCENES, scenes_copy)


class TestPlanAssetStrategyIncludesSceneShot(unittest.TestCase):
    """Sprint79 - plan_asset_strategy()의 결과 dict에 scene_shot이
    함께 실려야 한다(기존 scene/prefer_ai/visual_profile/scene_role
    필드에 추가)."""

    def test_plan_includes_scene_shot_for_every_scene(self):
        plan = plan_asset_strategy(SIX_SCENES)

        for strategy in plan.values():
            self.assertIn("scene_shot", strategy)
            self.assertIn(strategy["scene_shot"], SCENE_SHOT_TYPES)

    def test_plan_scene_shot_matches_assign_scene_shots(self):
        plan = plan_asset_strategy(SIX_SCENES)

        expected = assign_scene_shots(SIX_SCENES)

        for scene_number, strategy in plan.items():
            self.assertEqual(strategy["scene_shot"], expected[scene_number])

    def test_plan_result_still_json_serializable_with_scene_shot(self):
        plan = plan_asset_strategy(SIX_SCENES)

        json.dumps(plan)


if __name__ == "__main__":
    unittest.main()
