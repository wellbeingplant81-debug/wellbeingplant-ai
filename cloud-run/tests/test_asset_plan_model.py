import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from pydantic import ValidationError

from app.models.asset_plan import AssetPlan, SceneAssetStrategy, VisualProfile


SAMPLE_PROFILE = {
    "camera_distance": "wide",
    "camera_angle": "eye level",
    "composition": "centered",
    "lighting": "soft daylight",
}


class TestVisualProfile(unittest.TestCase):

    def test_valid_profile_constructs(self):
        profile = VisualProfile(**SAMPLE_PROFILE)
        self.assertEqual(profile.camera_distance, "wide")

    def test_missing_field_raises(self):
        incomplete = dict(SAMPLE_PROFILE)
        del incomplete["lighting"]

        with self.assertRaises(ValidationError):
            VisualProfile(**incomplete)


class TestSceneAssetStrategy(unittest.TestCase):

    def test_valid_strategy_constructs(self):
        strategy = SceneAssetStrategy(
            scene=1, prefer_ai=True, visual_profile=SAMPLE_PROFILE,
            scene_role="hero", scene_shot="wide",
        )
        self.assertEqual(strategy.scene, 1)
        self.assertTrue(strategy.prefer_ai)
        self.assertEqual(strategy.visual_profile.camera_distance, "wide")

    def test_model_dump_is_plain_json_serializable_dict(self):
        import json

        strategy = SceneAssetStrategy(
            scene=1, prefer_ai=False, visual_profile=SAMPLE_PROFILE,
            scene_role="detail", scene_shot="medium",
        )
        dumped = strategy.model_dump()

        self.assertEqual(dumped["scene"], 1)
        self.assertEqual(dumped["prefer_ai"], False)
        self.assertEqual(dumped["visual_profile"], SAMPLE_PROFILE)
        self.assertEqual(dumped["scene_role"], "detail")
        self.assertEqual(dumped["scene_shot"], "medium")
        # 예외 없이 직렬화 가능해야 pipeline.py의 json.dump(data, ...)와 호환된다.
        json.dumps(dumped)

    def test_missing_scene_raises(self):
        with self.assertRaises(ValidationError):
            SceneAssetStrategy(prefer_ai=True, visual_profile=SAMPLE_PROFILE)


class TestAssetPlan(unittest.TestCase):

    def test_holds_strategies_keyed_by_scene_number(self):
        plan = AssetPlan(strategies={
            1: SceneAssetStrategy(
                scene=1, prefer_ai=True, visual_profile=SAMPLE_PROFILE,
                scene_role="hero", scene_shot="wide",
            ),
        })
        self.assertIn(1, plan.strategies)
        self.assertEqual(plan.strategies[1].scene, 1)


if __name__ == "__main__":
    unittest.main()
