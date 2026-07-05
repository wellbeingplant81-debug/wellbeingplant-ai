import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.prompt_styler import (
    annotate_scenes_with_style,
    apply_style_to_prompt,
)
from app.services.style_profile_builder import build_style_profile, style_profile_to_text


PROFILE = build_style_profile()


class TestApplyStyleToPrompt(unittest.TestCase):

    def test_appends_style_text_to_prompt(self):
        result = apply_style_to_prompt("a photo of a cup", PROFILE)

        self.assertTrue(result.startswith("a photo of a cup"))
        self.assertIn(style_profile_to_text(PROFILE), result)

    def test_empty_prompt_returned_unchanged(self):
        self.assertEqual(apply_style_to_prompt("", PROFILE), "")

    def test_does_not_double_apply_style(self):
        once = apply_style_to_prompt("a photo of a cup", PROFILE)
        twice = apply_style_to_prompt(once, PROFILE)

        self.assertEqual(once, twice)
        self.assertEqual(twice.count(style_profile_to_text(PROFILE)), 1)


class TestAnnotateScenesWithStyle(unittest.TestCase):

    def test_applies_style_to_every_scene(self):
        scenes = [
            {"scene": 1, "image_prompt": "prompt one"},
            {"scene": 2, "image_prompt": "prompt two"},
        ]
        result = annotate_scenes_with_style(scenes, PROFILE)

        style_text = style_profile_to_text(PROFILE)
        for scene in result:
            self.assertIn(style_text, scene["image_prompt"])

    def test_all_scenes_share_the_same_style_text(self):
        scenes = [
            {"scene": 1, "image_prompt": "prompt one"},
            {"scene": 2, "image_prompt": "prompt two"},
        ]
        result = annotate_scenes_with_style(scenes, PROFILE)
        style_text = style_profile_to_text(PROFILE)

        self.assertTrue(all(style_text in s["image_prompt"] for s in result))

    def test_original_scenes_not_mutated(self):
        scenes = [{"scene": 1, "image_prompt": "prompt one"}]
        scenes_copy = [dict(s) for s in scenes]

        annotate_scenes_with_style(scenes_copy, PROFILE)

        self.assertEqual(scenes_copy, scenes)

    def test_scene_order_preserved(self):
        scenes = [
            {"scene": 1, "image_prompt": "p1"},
            {"scene": 2, "image_prompt": "p2"},
            {"scene": 3, "image_prompt": "p3"},
        ]
        result = annotate_scenes_with_style(scenes, PROFILE)

        self.assertEqual([s["scene"] for s in result], [1, 2, 3])

    def test_other_fields_preserved(self):
        scenes = [{"scene": 1, "image_prompt": "p1", "narration": "n1"}]
        result = annotate_scenes_with_style(scenes, PROFILE)

        self.assertEqual(result[0]["narration"], "n1")

    def test_empty_scene_list_returns_empty(self):
        self.assertEqual(annotate_scenes_with_style([], PROFILE), [])


if __name__ == "__main__":
    unittest.main()
