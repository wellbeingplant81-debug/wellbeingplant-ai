import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import prompt_learning_service
from app.services.prompt_learning_service import PromptLearningEngine


LIFESTYLE_SCENE = {
    "scene": 1,
    "narration": "오늘 아침 상쾌하게 산책을 했어요",
    "image_prompt": "a happy woman walking outside in the morning",
}

MEDICAL_SCENE = {
    "scene": 2,
    "narration": "혈관 건강이 왜 중요한지 아시나요",
    "image_prompt": "diagram of blood vessel anatomy",
}

PLAN_FOR_SCENE_1 = {
    "scene_id": 1, "purpose": "hook", "visual_type": "photo_realistic",
    "camera": "close_up", "transition": "fade", "duration": 3.0,
    "keywords": ["woman", "walking", "morning"],
}

PLAN_FOR_SCENE_2 = {
    "scene_id": 2, "purpose": "development", "visual_type": "illustrative",
    "camera": "wide_shot", "transition": "cross_dissolve", "duration": 4.0,
    "keywords": ["blood", "vessel", "anatomy"],
}


def _passed(scene_id, score=95):
    return {"scene_id": scene_id, "score": score, "passed": True, "metrics": {}}


def _failed(scene_id, score=40):
    return {"scene_id": scene_id, "score": score, "passed": False, "metrics": {}}


class TestLearnFromScenesPassFail(unittest.TestCase):

    def setUp(self):
        self.engine = PromptLearningEngine()

    def test_passed_prompt_is_learned(self):
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [_passed(1)],
        )

        summary = self.engine.get_learning_summary()
        self.assertEqual(summary["success_count"], 1)
        self.assertEqual(summary["camera_frequency"], {"close_up": 1})

    def test_failed_prompt_is_ignored(self):
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [_failed(1)],
        )

        summary = self.engine.get_learning_summary()
        self.assertEqual(summary["success_count"], 0)
        self.assertEqual(summary["camera_frequency"], {})

    def test_scene_with_no_matching_metrics_is_ignored(self):
        self.engine.learn_from_scenes([LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [])

        summary = self.engine.get_learning_summary()
        self.assertEqual(summary["success_count"], 0)

    def test_mixed_batch_only_learns_passed_scene(self):
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE, MEDICAL_SCENE],
            [PLAN_FOR_SCENE_1, PLAN_FOR_SCENE_2],
            [_passed(1), _failed(2)],
        )

        summary = self.engine.get_learning_summary()
        self.assertEqual(summary["success_count"], 1)
        self.assertIn("close_up", summary["camera_frequency"])
        self.assertNotIn("wide_shot", summary["camera_frequency"])


class TestStatisticsAccumulation(unittest.TestCase):

    def setUp(self):
        self.engine = PromptLearningEngine()

    def test_repeated_learning_accumulates_counts(self):
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [_passed(1, score=90)],
        )
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [_passed(1, score=100)],
        )

        summary = self.engine.get_learning_summary()
        self.assertEqual(summary["success_count"], 2)
        self.assertEqual(summary["camera_frequency"]["close_up"], 2)
        self.assertEqual(summary["average_score"], 95.0)

    def test_keyword_frequency_accumulates_per_keyword(self):
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [_passed(1)],
        )
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [_passed(1)],
        )

        summary = self.engine.get_learning_summary()
        self.assertEqual(summary["keyword_frequency"]["woman"], 2)
        self.assertEqual(summary["keyword_frequency"]["walking"], 2)

    def test_scene_category_frequency_distinguishes_medical_from_lifestyle(self):
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE, MEDICAL_SCENE],
            [PLAN_FOR_SCENE_1, PLAN_FOR_SCENE_2],
            [_passed(1), _passed(2)],
        )

        summary = self.engine.get_learning_summary()
        self.assertEqual(summary["scene_category_frequency"]["pexels_priority"], 1)
        self.assertEqual(summary["scene_category_frequency"]["ai_priority"], 1)


class TestBestPatternRetrieval(unittest.TestCase):

    def setUp(self):
        self.engine = PromptLearningEngine()

    def test_no_data_returns_none_fields_and_empty_keywords(self):
        pattern = self.engine.get_best_pattern()

        self.assertIsNone(pattern["camera"])
        self.assertIsNone(pattern["visual_type"])
        self.assertIsNone(pattern["purpose"])
        self.assertIsNone(pattern["scene_category"])
        self.assertEqual(pattern["keywords"], [])

    def test_most_frequent_values_are_returned(self):
        self.engine.learn_from_scenes(
            [LIFESTYLE_SCENE, LIFESTYLE_SCENE, MEDICAL_SCENE],
            [PLAN_FOR_SCENE_1, PLAN_FOR_SCENE_1, PLAN_FOR_SCENE_2],
            [_passed(1), _passed(1), _passed(2)],
        )

        pattern = self.engine.get_best_pattern()

        self.assertEqual(pattern["camera"], "close_up")
        self.assertEqual(pattern["visual_type"], "photo_realistic")
        self.assertEqual(pattern["purpose"], "hook")
        self.assertEqual(pattern["scene_category"], "pexels_priority")
        self.assertIn("woman", pattern["keywords"])


class TestLearningSummaryGeneration(unittest.TestCase):

    def setUp(self):
        self.engine = PromptLearningEngine()

    def test_summary_has_expected_keys(self):
        summary = self.engine.get_learning_summary()
        self.assertEqual(
            set(summary.keys()),
            {"success_count", "average_score", "camera_frequency",
             "visual_type_frequency", "purpose_frequency",
             "keyword_frequency", "scene_category_frequency"},
        )

    def test_empty_summary_has_zero_success_and_zero_average(self):
        summary = self.engine.get_learning_summary()
        self.assertEqual(summary["success_count"], 0)
        self.assertEqual(summary["average_score"], 0.0)


class TestModuleLevelDefaultEngine(unittest.TestCase):

    def setUp(self):
        prompt_learning_service.reset_learning()
        self.addCleanup(prompt_learning_service.reset_learning)

    def test_flat_api_delegates_to_default_engine(self):
        prompt_learning_service.learn_from_scenes(
            [LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [_passed(1)],
        )

        summary = prompt_learning_service.get_learning_summary()
        self.assertEqual(summary["success_count"], 1)

        pattern = prompt_learning_service.get_best_pattern()
        self.assertEqual(pattern["camera"], "close_up")

    def test_reset_learning_clears_default_engine_state(self):
        prompt_learning_service.learn_from_scenes(
            [LIFESTYLE_SCENE], [PLAN_FOR_SCENE_1], [_passed(1)],
        )
        prompt_learning_service.reset_learning()

        summary = prompt_learning_service.get_learning_summary()
        self.assertEqual(summary["success_count"], 0)


if __name__ == "__main__":
    unittest.main()
