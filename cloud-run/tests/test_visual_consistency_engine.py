import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.style_profile_builder import build_style_profile, style_profile_to_text
from app.services.visual_consistency_engine import apply_visual_consistency


class TestApplyVisualConsistency(unittest.TestCase):

    def test_injects_style_into_every_scene_prompt(self):
        scenes = [
            {"scene": 1, "image_prompt": "a woman opening curtains"},
            {"scene": 2, "image_prompt": "a bowl of oatmeal"},
        ]
        result = apply_visual_consistency(scenes, "wellbeing")

        style_text = style_profile_to_text(build_style_profile("wellbeing"))
        for scene in result:
            self.assertIn(style_text, scene["image_prompt"])

    def test_default_channel_is_wellbeing(self):
        scenes = [{"scene": 1, "image_prompt": "a woman opening curtains"}]
        result = apply_visual_consistency(scenes)

        style_text = style_profile_to_text(build_style_profile("wellbeing"))
        self.assertIn(style_text, result[0]["image_prompt"])

    def test_original_content_still_present(self):
        scenes = [{"scene": 1, "image_prompt": "a woman opening curtains"}]
        result = apply_visual_consistency(scenes, "wellbeing")

        self.assertIn("a woman opening curtains", result[0]["image_prompt"])

    def test_does_not_touch_other_fields(self):
        scenes = [
            {
                "scene": 1,
                "image_prompt": "a woman opening curtains",
                "narration": "n1",
                "search_query": "q1",
            }
        ]
        result = apply_visual_consistency(scenes, "wellbeing")

        self.assertEqual(result[0]["narration"], "n1")
        self.assertEqual(result[0]["search_query"], "q1")

    def test_original_scenes_not_mutated(self):
        scenes = [{"scene": 1, "image_prompt": "a woman opening curtains"}]
        scenes_copy = [dict(s) for s in scenes]

        apply_visual_consistency(scenes_copy, "wellbeing")

        self.assertEqual(scenes_copy, scenes)

    def test_scene_count_and_order_preserved(self):
        scenes = [
            {"scene": 1, "image_prompt": "p1"},
            {"scene": 2, "image_prompt": "p2"},
            {"scene": 3, "image_prompt": "p3"},
        ]
        result = apply_visual_consistency(scenes, "wellbeing")

        self.assertEqual([s["scene"] for s in result], [1, 2, 3])

    def test_all_scenes_get_identical_style_text(self):
        scenes = [
            {"scene": 1, "image_prompt": "p1"},
            {"scene": 2, "image_prompt": "p2"},
        ]
        result = apply_visual_consistency(scenes, "wellbeing")
        style_text = style_profile_to_text(build_style_profile("wellbeing"))

        suffixes = [
            scene["image_prompt"].split(original)[-1]
            for scene, original in zip(result, ["p1", "p2"])
        ]
        self.assertEqual(suffixes[0], suffixes[1])
        self.assertIn(style_text, suffixes[0])


if __name__ == "__main__":
    unittest.main()
