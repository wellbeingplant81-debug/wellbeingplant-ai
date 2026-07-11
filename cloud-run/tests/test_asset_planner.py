import json
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_planner import plan_asset_strategy
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


if __name__ == "__main__":
    unittest.main()
