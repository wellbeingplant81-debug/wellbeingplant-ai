import copy
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import prompt_effectiveness_service
from app.services import prompt_optimization_service


ORIGINAL_PROMPT = "a tired woman resting at home"

FULL_PLAN_ITEM = {
    "scene_id": 1,
    "purpose": "hook",
    "visual_type": "photo_realistic",
    "camera": "close_up",
    "transition": "fade",
    "duration": 3.0,
    "keywords": ["tired", "woman", "home"],
}


def _passing_evaluation(**overrides):
    """
    prompt_effectiveness_service.evaluate_prompt()이 실제로 만들어낼
    법한 evaluation dict를 흉내낸다. length/keywords는 숫자 메트릭이므로
    실제 임계값(MIN/MAX_PROMPT_LENGTH, MIN_KEYWORD_COUNT)으로 통과
    여부를 계산해야 "passed"가 실제 서비스와 같은 규칙으로 나온다.
    """
    metrics = {
        "prompt_preserved": True,
        "camera": True,
        "visual_type": True,
        "purpose": True,
        "length": 50,
        "keywords": 3,
        "duplicate_free": True,
    }
    metrics.update(overrides)

    length_ok = (
        prompt_effectiveness_service.MIN_PROMPT_LENGTH
        <= metrics["length"]
        <= prompt_effectiveness_service.MAX_PROMPT_LENGTH
    )
    keywords_ok = metrics["keywords"] >= prompt_effectiveness_service.MIN_KEYWORD_COUNT

    passed = length_ok and keywords_ok and all(
        v is True for k, v in metrics.items() if k not in ("length", "keywords")
    )

    return {"score": 100 if passed else 0, "passed": passed, "metrics": metrics}


class TestOptimizePromptPassthrough(unittest.TestCase):

    def test_passed_evaluation_returns_prompt_unchanged(self):
        enriched = f"{ORIGINAL_PROMPT}, close-up, photo realistic, hook"
        evaluation = {"score": 100, "passed": True, "metrics": {}}

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertEqual(result, enriched)

    def test_none_evaluation_returns_prompt_unchanged(self):
        enriched = f"{ORIGINAL_PROMPT}, close-up"
        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, None, FULL_PLAN_ITEM,
        )
        self.assertEqual(result, enriched)

    def test_empty_prompt_stays_empty(self):
        evaluation = _passing_evaluation(camera=False)
        result = prompt_optimization_service.optimize_prompt(
            "", "", evaluation, FULL_PLAN_ITEM,
        )
        self.assertEqual(result, "")


class TestOptimizePromptRules(unittest.TestCase):

    def test_missing_camera_phrase_is_added(self):
        enriched = f"{ORIGINAL_PROMPT}, photo realistic, hook"
        evaluation = _passing_evaluation(camera=False)

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertIn("close-up", result)
        self.assertIn(ORIGINAL_PROMPT, result)

    def test_missing_visual_type_phrase_is_added(self):
        enriched = f"{ORIGINAL_PROMPT}, close-up, hook"
        evaluation = _passing_evaluation(visual_type=False)

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertIn("photo realistic", result)

    def test_missing_purpose_phrase_is_added(self):
        enriched = f"{ORIGINAL_PROMPT}, close-up, photo realistic"
        evaluation = _passing_evaluation(purpose=False)

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertIn("hook", result)

    def test_does_not_duplicate_phrase_already_present(self):
        enriched = f"{ORIGINAL_PROMPT}, close-up, photo realistic, hook"
        evaluation = _passing_evaluation(camera=False)

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertEqual(result.count("close-up"), 1)

    def test_missing_prompt_preserved_reinserts_original(self):
        enriched = "a completely different prompt"
        evaluation = _passing_evaluation(prompt_preserved=False)

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertIn(ORIGINAL_PROMPT, result)
        self.assertIn(enriched, result)

    def test_unknown_camera_value_is_not_added(self):
        enriched = f"{ORIGINAL_PROMPT}, photo realistic, hook"
        plan_item = {**FULL_PLAN_ITEM, "camera": "drone_shot"}
        evaluation = _passing_evaluation(camera=False)

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, plan_item,
        )

        self.assertEqual(result, enriched)


class TestOptimizePromptDuplicateRemoval(unittest.TestCase):

    def test_duplicate_fragment_is_removed(self):
        enriched = f"{ORIGINAL_PROMPT}, photo realistic, hook, photo realistic"
        evaluation = _passing_evaluation(duplicate_free=False)

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertEqual(result.count("photo realistic"), 1)
        self.assertIn(ORIGINAL_PROMPT, result)

    def test_duplicate_removal_is_case_insensitive(self):
        enriched = f"{ORIGINAL_PROMPT}, Hook, hook"
        evaluation = _passing_evaluation(duplicate_free=False)

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        fragments = [f.strip().lower() for f in result.split(",")]
        self.assertEqual(len(fragments), len(set(fragments)))


class TestOptimizePromptLengthTrim(unittest.TestCase):

    def test_excessive_length_is_trimmed(self):
        enriched = ORIGINAL_PROMPT + "," + ("x" * 600)
        evaluation = _passing_evaluation(length=len(enriched))

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertLessEqual(
            len(result), prompt_optimization_service.MAX_PROMPT_LENGTH,
        )
        self.assertIn(ORIGINAL_PROMPT, result)

    def test_never_trims_below_original_prompt_length(self):
        long_original = "a " + ("very " * 100) + "long original prompt"
        evaluation = _passing_evaluation(length=len(long_original))

        result = prompt_optimization_service.optimize_prompt(
            long_original, long_original, evaluation, FULL_PLAN_ITEM,
        )

        self.assertEqual(result, long_original)

    def test_within_limit_length_is_not_trimmed(self):
        enriched = f"{ORIGINAL_PROMPT}, close-up"
        evaluation = _passing_evaluation(length=len(enriched))

        result = prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, enriched, evaluation, FULL_PLAN_ITEM,
        )

        self.assertEqual(result, enriched)


class TestOptimizePromptImmutability(unittest.TestCase):

    def test_does_not_mutate_evaluation_or_scene_plan_item(self):
        evaluation = _passing_evaluation(camera=False)
        evaluation_copy = copy.deepcopy(evaluation)
        plan_copy = copy.deepcopy(FULL_PLAN_ITEM)

        prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, f"{ORIGINAL_PROMPT}, hook", evaluation, FULL_PLAN_ITEM,
        )

        self.assertEqual(evaluation, evaluation_copy)
        self.assertEqual(FULL_PLAN_ITEM, plan_copy)

    def test_preserves_original_keywords_metadata(self):
        """scene_plan_item의 keywords는 prompt 문자열 조작과 무관하게
        절대 읽거나 바꾸지 않아야 한다."""

        evaluation = _passing_evaluation(camera=False)
        plan_item = copy.deepcopy(FULL_PLAN_ITEM)

        prompt_optimization_service.optimize_prompt(
            ORIGINAL_PROMPT, f"{ORIGINAL_PROMPT}, hook", evaluation, plan_item,
        )

        self.assertEqual(plan_item["keywords"], ["tired", "woman", "home"])


class TestOptimizeScenesBatch(unittest.TestCase):

    def test_matches_by_scene_number_and_preserves_order_and_fields(self):
        original_scenes = [
            {"scene": 1, "narration": "n1", "image_prompt": ORIGINAL_PROMPT},
            {"scene": 2, "narration": "n2", "image_prompt": "a happy man walking"},
        ]
        enriched_scenes = [
            {"scene": 1, "narration": "n1", "image_prompt": f"{ORIGINAL_PROMPT}, photo realistic, hook", "provider": "ai_image"},
            {"scene": 2, "narration": "n2", "image_prompt": "a happy man walking", "provider": "pexels_image"},
        ]
        prompt_metrics = [
            {"scene_id": 1, "score": 70, "passed": False, "metrics": {
                "prompt_preserved": True, "camera": False, "visual_type": True,
                "purpose": True, "length": 40, "keywords": 3, "duplicate_free": True,
            }},
            {"scene_id": 2, "score": 100, "passed": True, "metrics": {}},
        ]
        scene_plan = [
            {"scene_id": 1, **{k: v for k, v in FULL_PLAN_ITEM.items() if k != "scene_id"}},
            {"scene_id": 2, "camera": "medium_shot", "visual_type": "photo_realistic", "purpose": "cta", "keywords": ["k"]},
        ]

        result = prompt_optimization_service.optimize_scenes(
            original_scenes, enriched_scenes, prompt_metrics, scene_plan,
        )

        self.assertEqual([s["scene"] for s in result], [1, 2])
        self.assertIn("close-up", result[0]["image_prompt"])
        self.assertEqual(result[1]["image_prompt"], "a happy man walking")
        self.assertEqual(result[0]["provider"], "ai_image")
        self.assertEqual(result[0]["narration"], "n1")

    def test_scene_without_metrics_is_unchanged(self):
        scenes = [{"scene": 1, "narration": "n1", "image_prompt": "p1"}]
        result = prompt_optimization_service.optimize_scenes(scenes, scenes, [], [])
        self.assertEqual(result[0]["image_prompt"], "p1")

    def test_does_not_mutate_input_scenes(self):
        scenes = [{"scene": 1, "narration": "n1", "image_prompt": "p1"}]
        scenes_copy = copy.deepcopy(scenes)

        prompt_optimization_service.optimize_scenes(scenes, scenes, [], [])

        self.assertEqual(scenes, scenes_copy)

    def test_empty_inputs_return_empty_list(self):
        self.assertEqual(
            prompt_optimization_service.optimize_scenes([], [], [], []), [],
        )
        self.assertEqual(
            prompt_optimization_service.optimize_scenes(None, None, None, None), [],
        )


if __name__ == "__main__":
    unittest.main()
