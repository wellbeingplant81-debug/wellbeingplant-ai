import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import ai_director_service


PASSED_PROMPT = {"scene_id": 1, "score": 100, "passed": True, "metrics": {}}
FAILED_PROMPT = {"scene_id": 1, "score": 40, "passed": False, "metrics": {}}

PASSED_ASSET = {"score": 95, "passed": True, "reasons": []}
BORDERLINE_ASSET = {"score": 70, "passed": False, "reasons": ["low_prompt_match"]}
FAILED_ASSET = {"score": 30, "passed": False, "reasons": ["asset_missing"]}

PLAN_ITEM = {
    "scene_id": 1, "purpose": "hook", "visual_type": "photo_realistic",
    "camera": "close_up", "transition": "fade", "duration": 3.0,
    "keywords": ["k1"],
}

BEST_PATTERN = {
    "camera": "close_up", "visual_type": "photo_realistic", "purpose": "hook",
    "keywords": ["k1"], "scene_category": "pexels_priority",
}


class TestAcceptDecision(unittest.TestCase):

    def test_prompt_passed_and_asset_passed_is_accept(self):
        result = ai_director_service.evaluate_scene(PASSED_PROMPT, PASSED_ASSET)
        self.assertEqual(result["decision"], "accept")

    def test_prompt_passed_and_asset_unknown_is_accept(self):
        result = ai_director_service.evaluate_scene(PASSED_PROMPT, None)
        self.assertEqual(result["decision"], "accept")

    def test_accept_with_known_pattern_includes_reason(self):
        result = ai_director_service.evaluate_scene(
            PASSED_PROMPT, PASSED_ASSET, PLAN_ITEM, BEST_PATTERN,
        )
        self.assertEqual(result["decision"], "accept")
        self.assertIn("known_successful_pattern", result["reasons"])


class TestReviewDecision(unittest.TestCase):

    def test_prompt_passed_and_asset_borderline_is_review(self):
        result = ai_director_service.evaluate_scene(PASSED_PROMPT, BORDERLINE_ASSET)
        self.assertEqual(result["decision"], "review")
        self.assertIn("asset_quality_borderline", result["reasons"])

    def test_prompt_unknown_and_asset_unknown_is_review(self):
        result = ai_director_service.evaluate_scene(None, None)
        self.assertEqual(result["decision"], "review")

    def test_failed_prompt_that_was_optimized_downgrades_to_review(self):
        result = ai_director_service.evaluate_scene(
            FAILED_PROMPT, PASSED_ASSET, optimized=True,
        )
        self.assertEqual(result["decision"], "review")
        self.assertIn("prompt_was_optimized", result["reasons"])


class TestRegenerateDecision(unittest.TestCase):

    def test_prompt_failed_is_regenerate(self):
        result = ai_director_service.evaluate_scene(FAILED_PROMPT, PASSED_ASSET)
        self.assertEqual(result["decision"], "regenerate")
        self.assertIn("prompt_failed", result["reasons"])

    def test_asset_quality_failed_is_regenerate(self):
        result = ai_director_service.evaluate_scene(PASSED_PROMPT, FAILED_ASSET)
        self.assertEqual(result["decision"], "regenerate")
        self.assertIn("asset_quality_failed", result["reasons"])

    def test_asset_quality_failed_even_when_optimized_stays_regenerate(self):
        """asset이 완전히 실패하면 optimized 여부와 무관하게 regenerate
        유지 - Optimization은 프롬프트만 손볼 뿐 asset 문제는 못 고친다."""

        result = ai_director_service.evaluate_scene(
            FAILED_PROMPT, FAILED_ASSET, optimized=True,
        )
        self.assertEqual(result["decision"], "regenerate")


class TestConfidenceCalculation(unittest.TestCase):

    def test_full_data_high_scores_yields_high_confidence(self):
        result = ai_director_service.evaluate_scene(PASSED_PROMPT, PASSED_ASSET)
        self.assertAlmostEqual(result["confidence"], (100 / 100 + 95 / 100) / 2, places=4)

    def test_missing_data_yields_neutral_confidence(self):
        result = ai_director_service.evaluate_scene(None, None)
        self.assertEqual(result["confidence"], 0.5)

    def test_pattern_match_adds_bonus_capped_at_one(self):
        result = ai_director_service.evaluate_scene(
            PASSED_PROMPT, PASSED_ASSET, PLAN_ITEM, BEST_PATTERN,
        )
        expected = min(1.0, (100 / 100 + 95 / 100) / 2 + 0.1)
        self.assertAlmostEqual(result["confidence"], expected, places=4)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_confidence_always_within_bounds(self):
        for prompt, asset in [
            (PASSED_PROMPT, PASSED_ASSET), (FAILED_PROMPT, FAILED_ASSET),
            (None, None), (PASSED_PROMPT, None), (None, FAILED_ASSET),
        ]:
            result = ai_director_service.evaluate_scene(prompt, asset)
            self.assertGreaterEqual(result["confidence"], 0.0)
            self.assertLessEqual(result["confidence"], 1.0)


class TestReasonGeneration(unittest.TestCase):

    def test_reasons_always_include_prompt_and_asset_status(self):
        result = ai_director_service.evaluate_scene(PASSED_PROMPT, PASSED_ASSET)
        self.assertIn("prompt_passed", result["reasons"])
        self.assertIn("asset_quality_passed", result["reasons"])

    def test_reasons_reflect_unknown_states(self):
        result = ai_director_service.evaluate_scene(None, None)
        self.assertIn("prompt_unknown", result["reasons"])
        self.assertIn("asset_quality_unknown", result["reasons"])

    def test_pattern_mismatch_does_not_add_reason(self):
        mismatched_plan = {**PLAN_ITEM, "camera": "wide_shot"}
        result = ai_director_service.evaluate_scene(
            PASSED_PROMPT, PASSED_ASSET, mismatched_plan, BEST_PATTERN,
        )
        self.assertNotIn("known_successful_pattern", result["reasons"])


class TestMissingMetrics(unittest.TestCase):

    def test_all_inputs_missing_still_returns_valid_structure(self):
        result = ai_director_service.evaluate_scene()
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["confidence"], 0.5)
        self.assertEqual(result["reasons"], ["prompt_unknown", "asset_quality_unknown"])

    def test_best_pattern_missing_does_not_crash(self):
        result = ai_director_service.evaluate_scene(
            PASSED_PROMPT, PASSED_ASSET, PLAN_ITEM, None,
        )
        self.assertEqual(result["decision"], "accept")

    def test_scene_plan_item_missing_does_not_crash(self):
        result = ai_director_service.evaluate_scene(
            PASSED_PROMPT, PASSED_ASSET, None, BEST_PATTERN,
        )
        self.assertEqual(result["decision"], "accept")


class TestEvaluateScenesBatch(unittest.TestCase):

    def test_matches_by_scene_number_and_preserves_order(self):
        scenes = [
            {"scene": 1, "narration": "n1", "image_prompt": "p1"},
            {"scene": 2, "narration": "n2", "image_prompt": "p2"},
        ]
        scene_plan = [PLAN_ITEM, {**PLAN_ITEM, "scene_id": 2, "camera": "wide_shot"}]
        prompt_metrics = [
            {"scene_id": 1, "score": 100, "passed": True, "metrics": {}},
            {"scene_id": 2, "score": 40, "passed": False, "metrics": {}},
        ]

        results = ai_director_service.evaluate_scenes(scenes, scene_plan, prompt_metrics)

        self.assertEqual([r["scene_id"] for r in results], [1, 2])
        self.assertEqual(results[0]["decision"], "accept")
        self.assertEqual(results[1]["decision"], "regenerate")

    def test_empty_inputs_return_empty_list(self):
        self.assertEqual(ai_director_service.evaluate_scenes([]), [])
        self.assertEqual(ai_director_service.evaluate_scenes(None), [])

    def test_does_not_mutate_input_scenes(self):
        import copy
        scenes = [{"scene": 1, "narration": "n1", "image_prompt": "p1"}]
        scenes_copy = copy.deepcopy(scenes)

        ai_director_service.evaluate_scenes(scenes, [], [])

        self.assertEqual(scenes, scenes_copy)

    def test_optimized_scene_ids_passed_through_to_reasons(self):
        scenes = [{"scene": 1, "narration": "n1", "image_prompt": "p1"}]
        prompt_metrics = [{"scene_id": 1, "score": 40, "passed": False, "metrics": {}}]

        results = ai_director_service.evaluate_scenes(
            scenes, [], prompt_metrics, optimized_scene_ids={1},
        )

        self.assertIn("prompt_was_optimized", results[0]["reasons"])
        self.assertEqual(results[0]["decision"], "review")


if __name__ == "__main__":
    unittest.main()
