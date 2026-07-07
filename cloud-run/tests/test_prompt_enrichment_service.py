import copy
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import prompt_enrichment_service


FULL_PLAN_ITEM = {
    "scene_id": 1,
    "purpose": "hook",
    "visual_type": "photo_realistic",
    "camera": "close_up",
    "transition": "fade",
    "duration": 3.0,
    "keywords": ["tired", "woman"],
}


class TestEnrichPrompt(unittest.TestCase):

    def test_original_prompt_is_preserved(self):
        result = prompt_enrichment_service.enrich_prompt(
            "a tired woman resting at home", FULL_PLAN_ITEM,
        )
        self.assertTrue(result.startswith("a tired woman resting at home"))

    def test_camera_descriptor_added_close_up(self):
        result = prompt_enrichment_service.enrich_prompt("p", FULL_PLAN_ITEM)
        self.assertIn("close-up", result)

    def test_camera_descriptor_added_wide_shot(self):
        item = {**FULL_PLAN_ITEM, "camera": "wide_shot"}
        result = prompt_enrichment_service.enrich_prompt("p", item)
        self.assertIn("wide shot", result)

    def test_camera_descriptor_added_medium_shot(self):
        item = {**FULL_PLAN_ITEM, "camera": "medium_shot"}
        result = prompt_enrichment_service.enrich_prompt("p", item)
        self.assertIn("medium shot", result)

    def test_visual_type_descriptor_added_photo_realistic(self):
        result = prompt_enrichment_service.enrich_prompt("p", FULL_PLAN_ITEM)
        self.assertIn("photo realistic", result)

    def test_visual_type_descriptor_added_illustrative(self):
        item = {**FULL_PLAN_ITEM, "visual_type": "illustrative"}
        result = prompt_enrichment_service.enrich_prompt("p", item)
        self.assertIn("illustrative", result)

    def test_purpose_descriptor_added_hook(self):
        result = prompt_enrichment_service.enrich_prompt("p", FULL_PLAN_ITEM)
        self.assertIn("hook", result)

    def test_purpose_descriptor_added_development(self):
        item = {**FULL_PLAN_ITEM, "purpose": "development"}
        result = prompt_enrichment_service.enrich_prompt("p", item)
        self.assertIn("development", result)

    def test_purpose_descriptor_added_cta(self):
        item = {**FULL_PLAN_ITEM, "purpose": "cta"}
        result = prompt_enrichment_service.enrich_prompt("p", item)
        self.assertIn("cta", result)

    def test_planner_disabled_none_scene_plan_item_returns_original_unchanged(self):
        result = prompt_enrichment_service.enrich_prompt("a tired woman", None)
        self.assertEqual(result, "a tired woman")

    def test_empty_scene_plan_item_returns_original_unchanged(self):
        result = prompt_enrichment_service.enrich_prompt("a tired woman", {})
        self.assertEqual(result, "a tired woman")

    def test_unknown_field_values_are_ignored_and_prompt_unchanged(self):
        item = {"camera": "drone_shot", "visual_type": "3d_render", "purpose": "outro"}
        result = prompt_enrichment_service.enrich_prompt("a tired woman", item)
        self.assertEqual(result, "a tired woman")

    def test_empty_prompt_still_gets_enriched(self):
        result = prompt_enrichment_service.enrich_prompt("", FULL_PLAN_ITEM)
        self.assertEqual(result, "close-up, photo realistic, hook")

    def test_empty_prompt_with_empty_scene_plan_item_stays_empty(self):
        result = prompt_enrichment_service.enrich_prompt("", {})
        self.assertEqual(result, "")

    def test_does_not_mutate_scene_plan_item(self):
        item_copy = copy.deepcopy(FULL_PLAN_ITEM)
        prompt_enrichment_service.enrich_prompt("p", FULL_PLAN_ITEM)
        self.assertEqual(FULL_PLAN_ITEM, item_copy)


class TestApplyPromptEnrichment(unittest.TestCase):

    def test_matches_scene_plan_by_scene_id_and_preserves_order(self):
        scenes = [
            {"scene": 1, "narration": "n1", "image_prompt": "p1"},
            {"scene": 2, "narration": "n2", "image_prompt": "p2"},
        ]
        scene_plan = [
            {"scene_id": 1, "camera": "close_up", "visual_type": "photo_realistic", "purpose": "hook"},
            {"scene_id": 2, "camera": "medium_shot", "visual_type": "photo_realistic", "purpose": "cta"},
        ]

        result = prompt_enrichment_service.apply_prompt_enrichment(scenes, scene_plan)

        self.assertEqual([s["scene"] for s in result], [1, 2])
        self.assertIn("close-up", result[0]["image_prompt"])
        self.assertIn("medium shot", result[1]["image_prompt"])
        self.assertTrue(result[0]["image_prompt"].startswith("p1"))
        self.assertTrue(result[1]["image_prompt"].startswith("p2"))

    def test_scene_without_matching_plan_item_is_unchanged(self):
        scenes = [{"scene": 1, "narration": "n1", "image_prompt": "p1"}]
        result = prompt_enrichment_service.apply_prompt_enrichment(scenes, [])
        self.assertEqual(result[0]["image_prompt"], "p1")

    def test_does_not_mutate_input_scenes(self):
        scenes = [{"scene": 1, "narration": "n1", "image_prompt": "p1"}]
        scenes_copy = copy.deepcopy(scenes)
        scene_plan = [{"scene_id": 1, "camera": "close_up"}]

        prompt_enrichment_service.apply_prompt_enrichment(scenes, scene_plan)

        self.assertEqual(scenes, scenes_copy)

    def test_other_scene_fields_preserved(self):
        scenes = [{"scene": 1, "narration": "n1", "image_prompt": "p1", "provider": "ai_image"}]
        scene_plan = [{"scene_id": 1, "camera": "close_up"}]

        result = prompt_enrichment_service.apply_prompt_enrichment(scenes, scene_plan)

        self.assertEqual(result[0]["provider"], "ai_image")
        self.assertEqual(result[0]["narration"], "n1")


if __name__ == "__main__":
    unittest.main()
