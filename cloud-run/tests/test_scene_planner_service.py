import copy
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import scene_planner_service


THREE_SCENE_SCRIPT = {
    "title": "t",
    "hook": "h",
    "script": "s",
    "scenes": [
        {"scene": 1, "narration": "피곤한 하루였다.", "image_prompt": "tired woman resting at home"},
        {"scene": 2, "narration": "혈관 건강이 중요하다는 사실을 아는 사람은 많지 않다.", "image_prompt": "blood vessel diagram anatomy"},
        {"scene": 3, "narration": "오늘부터 작은 습관을 시작해보세요.", "image_prompt": "happy woman morning walk"},
    ],
}


class TestPlanScenesStructure(unittest.TestCase):

    def test_return_structure_has_expected_keys_and_types(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)

        for plan in plans:
            self.assertEqual(
                set(plan.keys()),
                {"scene_id", "purpose", "visual_type", "camera",
                 "transition", "duration", "keywords"},
            )
            self.assertIsInstance(plan["scene_id"], int)
            self.assertIsInstance(plan["purpose"], str)
            self.assertIsInstance(plan["visual_type"], str)
            self.assertIsInstance(plan["camera"], str)
            self.assertIsInstance(plan["transition"], str)
            self.assertIsInstance(plan["duration"], float)
            self.assertIsInstance(plan["keywords"], list)

    def test_scene_count_preserved(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual(len(plans), 3)

    def test_scene_order_and_scene_id_preserved(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual([p["scene_id"] for p in plans], [1, 2, 3])

    def test_does_not_mutate_input_script(self):
        script_copy = copy.deepcopy(THREE_SCENE_SCRIPT)
        scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual(THREE_SCENE_SCRIPT, script_copy)


class TestPurposeAndCamera(unittest.TestCase):

    def test_first_scene_is_hook_with_close_up_camera(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual(plans[0]["purpose"], "hook")
        self.assertEqual(plans[0]["camera"], "close_up")

    def test_middle_scene_is_development_with_wide_shot_camera(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual(plans[1]["purpose"], "development")
        self.assertEqual(plans[1]["camera"], "wide_shot")

    def test_last_scene_is_cta_with_medium_shot_camera(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual(plans[2]["purpose"], "cta")
        self.assertEqual(plans[2]["camera"], "medium_shot")

    def test_single_scene_script_is_hook(self):
        script = {"scenes": [{"scene": 1, "narration": "n", "image_prompt": "p"}]}
        plans = scene_planner_service.plan_scenes(script)
        self.assertEqual(plans[0]["purpose"], "hook")


class TestTransition(unittest.TestCase):

    def test_transition_matches_existing_transition_engine_rules(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual(plans[0]["transition"], "fade")
        self.assertEqual(plans[1]["transition"], "cross_dissolve")
        self.assertEqual(plans[2]["transition"], "cross_dissolve")


class TestVisualType(unittest.TestCase):

    def test_medical_scene_is_illustrative(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual(plans[1]["visual_type"], "illustrative")

    def test_lifestyle_scene_is_photo_realistic(self):
        plans = scene_planner_service.plan_scenes(THREE_SCENE_SCRIPT)
        self.assertEqual(plans[0]["visual_type"], "photo_realistic")
        self.assertEqual(plans[2]["visual_type"], "photo_realistic")


class TestDuration(unittest.TestCase):

    def test_duration_scales_with_narration_length(self):
        short_script = {"scenes": [{"scene": 1, "narration": "짧다", "image_prompt": "p"}]}
        long_script = {"scenes": [{"scene": 1, "narration": "가" * 60, "image_prompt": "p"}]}

        short_duration = scene_planner_service.plan_scenes(short_script)[0]["duration"]
        long_duration = scene_planner_service.plan_scenes(long_script)[0]["duration"]

        self.assertLess(short_duration, long_duration)

    def test_duration_formula_matches_chars_per_second_rate(self):
        narration = "가" * 55  # 55 / 5.5 = 10.0
        script = {"scenes": [{"scene": 1, "narration": narration, "image_prompt": "p"}]}

        duration = scene_planner_service.plan_scenes(script)[0]["duration"]

        self.assertEqual(duration, 10.0)

    def test_empty_narration_falls_back_to_minimum_duration(self):
        script = {"scenes": [{"scene": 1, "narration": "", "image_prompt": "p"}]}
        duration = scene_planner_service.plan_scenes(script)[0]["duration"]
        self.assertEqual(duration, scene_planner_service.MIN_SCENE_DURATION_SECONDS)


class TestKeywords(unittest.TestCase):

    def test_uses_existing_search_query_when_present(self):
        script = {
            "scenes": [
                {
                    "scene": 1,
                    "narration": "n",
                    "image_prompt": "should not be used",
                    "search_query": "already computed query",
                },
            ],
        }

        keywords = scene_planner_service.plan_scenes(script)[0]["keywords"]

        self.assertEqual(keywords, ["already", "computed", "query"])

    def test_falls_back_to_extracting_from_image_prompt(self):
        script = {
            "scenes": [
                {"scene": 1, "narration": "n", "image_prompt": "tired woman resting at home"},
            ],
        }

        keywords = scene_planner_service.plan_scenes(script)[0]["keywords"]

        self.assertTrue(len(keywords) > 0)
        self.assertIn("tired", keywords)

    def test_missing_image_prompt_and_search_query_returns_empty_keywords(self):
        script = {"scenes": [{"scene": 1, "narration": "n"}]}
        keywords = scene_planner_service.plan_scenes(script)[0]["keywords"]
        self.assertEqual(keywords, [])


class TestEmptyInput(unittest.TestCase):

    def test_none_script_returns_empty_list(self):
        self.assertEqual(scene_planner_service.plan_scenes(None), [])

    def test_empty_dict_returns_empty_list(self):
        self.assertEqual(scene_planner_service.plan_scenes({}), [])

    def test_empty_scenes_list_returns_empty_list(self):
        self.assertEqual(scene_planner_service.plan_scenes({"scenes": []}), [])


if __name__ == "__main__":
    unittest.main()
