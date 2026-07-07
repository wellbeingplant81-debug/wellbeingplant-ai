import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import prompt_effectiveness_service


FULL_PLAN_ITEM = {
    "scene_id": 1,
    "purpose": "hook",
    "visual_type": "photo_realistic",
    "camera": "close_up",
    "transition": "fade",
    "duration": 3.0,
    "keywords": ["tired", "woman", "home", "resting", "quiet"],
}

GOOD_ORIGINAL = "a tired woman resting at home"
GOOD_ENRICHED = f"{GOOD_ORIGINAL}, close-up, photo realistic, hook"


class TestEvaluatePromptScoring(unittest.TestCase):

    def test_all_checks_pass_scores_100(self):
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, GOOD_ENRICHED, FULL_PLAN_ITEM,
        )

        self.assertEqual(result["score"], 100)
        self.assertTrue(result["passed"])

    def test_metrics_returned_with_expected_keys_and_types(self):
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, GOOD_ENRICHED, FULL_PLAN_ITEM,
        )

        metrics = result["metrics"]
        self.assertEqual(
            set(metrics.keys()),
            {"prompt_preserved", "camera", "visual_type", "purpose",
             "length", "keywords", "duplicate_free"},
        )
        self.assertIsInstance(metrics["prompt_preserved"], bool)
        self.assertIsInstance(metrics["camera"], bool)
        self.assertIsInstance(metrics["visual_type"], bool)
        self.assertIsInstance(metrics["purpose"], bool)
        self.assertIsInstance(metrics["duplicate_free"], bool)
        self.assertIsInstance(metrics["length"], int)
        self.assertIsInstance(metrics["keywords"], int)
        self.assertEqual(metrics["length"], len(GOOD_ENRICHED))
        self.assertEqual(metrics["keywords"], 5)

    def test_prompt_not_preserved_fails_that_check(self):
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, "a completely different prompt", FULL_PLAN_ITEM,
        )

        self.assertFalse(result["metrics"]["prompt_preserved"])
        self.assertLess(result["score"], 100)

    def test_missing_camera_descriptor_fails_that_check(self):
        enriched = f"{GOOD_ORIGINAL}, photo realistic, hook"
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, enriched, FULL_PLAN_ITEM,
        )

        self.assertFalse(result["metrics"]["camera"])

    def test_missing_visual_type_descriptor_fails_that_check(self):
        enriched = f"{GOOD_ORIGINAL}, close-up, hook"
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, enriched, FULL_PLAN_ITEM,
        )

        self.assertFalse(result["metrics"]["visual_type"])

    def test_missing_purpose_descriptor_fails_that_check(self):
        enriched = f"{GOOD_ORIGINAL}, close-up, photo realistic"
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, enriched, FULL_PLAN_ITEM,
        )

        self.assertFalse(result["metrics"]["purpose"])

    def test_no_scene_plan_item_treats_descriptors_as_trivially_reflected(self):
        """Planner 비활성(scene_plan_item=None)이면 확인할 대상이 없으므로
        camera/visual_type/purpose는 통과 처리된다."""

        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, GOOD_ORIGINAL, None,
        )

        self.assertTrue(result["metrics"]["camera"])
        self.assertTrue(result["metrics"]["visual_type"])
        self.assertTrue(result["metrics"]["purpose"])
        self.assertEqual(result["metrics"]["keywords"], 0)


class TestEvaluatePromptBoundary(unittest.TestCase):

    def test_empty_prompt_and_empty_plan_scores_75_and_fails(self):
        """
        original/enriched가 둘 다 빈 문자열이고 scene_plan_item도 없으면:
        prompt_preserved(25) + camera(15) + visual_type(15) + purpose(15)
        + duplicate_free(5) = 75점만 얻는다 (length=0, keywords=0 실패).
        75 < PASS_THRESHOLD(80)이므로 FAIL - 임계값 미만 경계 확인.
        """

        result = prompt_effectiveness_service.evaluate_prompt("", "", {})

        self.assertEqual(result["score"], 75)
        self.assertFalse(result["passed"])
        self.assertFalse(result["metrics"]["keywords"] >= 1)

    def test_failing_camera_and_duplicate_only_scores_exactly_80_and_passes(self):
        """
        camera(15) + duplicate_free(5) = 20점만 잃으면 100-20=80점 -
        PASS_THRESHOLD(80)과 정확히 같아 통과해야 한다 (경계 포함 확인).
        """

        enriched = (
            f"{GOOD_ORIGINAL}, photo realistic, hook, photo realistic"
        )  # camera 문구 없음 + "photo realistic" 중복

        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, enriched, FULL_PLAN_ITEM,
        )

        self.assertEqual(result["score"], 80)
        self.assertTrue(result["passed"])
        self.assertFalse(result["metrics"]["camera"])
        self.assertFalse(result["metrics"]["duplicate_free"])


class TestEvaluatePromptEdgeCases(unittest.TestCase):

    def test_empty_prompt(self):
        result = prompt_effectiveness_service.evaluate_prompt("", "", FULL_PLAN_ITEM)
        self.assertEqual(result["metrics"]["length"], 0)
        self.assertTrue(result["metrics"]["prompt_preserved"])

    def test_duplicate_sentence_is_detected(self):
        enriched = "a tired woman, close-up, close-up, hook"
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, enriched, FULL_PLAN_ITEM,
        )
        self.assertFalse(result["metrics"]["duplicate_free"])

    def test_no_duplicate_sentence_passes(self):
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, GOOD_ENRICHED, FULL_PLAN_ITEM,
        )
        self.assertTrue(result["metrics"]["duplicate_free"])

    def test_long_prompt_fails_length_check(self):
        long_enriched = GOOD_ENRICHED + (" extremely detailed" * 30)
        result = prompt_effectiveness_service.evaluate_prompt(
            GOOD_ORIGINAL, long_enriched, FULL_PLAN_ITEM,
        )
        self.assertFalse(result["metrics"]["length"] <= prompt_effectiveness_service.MAX_PROMPT_LENGTH)
        self.assertLess(result["score"], 100)

    def test_too_short_prompt_fails_length_check(self):
        result = prompt_effectiveness_service.evaluate_prompt("hi", "hi", {})
        self.assertLess(result["metrics"]["length"], prompt_effectiveness_service.MIN_PROMPT_LENGTH)
        self.assertLess(result["score"], 100)


class TestEvaluateScenesBatch(unittest.TestCase):

    def test_matches_by_scene_number_and_preserves_order(self):
        original_scenes = [
            {"scene": 1, "image_prompt": GOOD_ORIGINAL},
            {"scene": 2, "image_prompt": "a happy man walking outside"},
        ]
        enriched_scenes = [
            {"scene": 1, "image_prompt": GOOD_ENRICHED},
            {"scene": 2, "image_prompt": "a happy man walking outside"},
        ]
        scene_plan = [
            {**FULL_PLAN_ITEM, "scene_id": 1},
            {**FULL_PLAN_ITEM, "scene_id": 2, "camera": "medium_shot"},
        ]

        results = prompt_effectiveness_service.evaluate_scenes(
            original_scenes, enriched_scenes, scene_plan,
        )

        self.assertEqual([r["scene_id"] for r in results], [1, 2])
        self.assertEqual(results[0]["score"], 100)

    def test_empty_inputs_return_empty_list(self):
        self.assertEqual(
            prompt_effectiveness_service.evaluate_scenes([], [], []), [],
        )
        self.assertEqual(
            prompt_effectiveness_service.evaluate_scenes(None, None, None), [],
        )


if __name__ == "__main__":
    unittest.main()
