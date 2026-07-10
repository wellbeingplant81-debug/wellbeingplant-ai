import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.visual_diversity_engine import (
    CAMERA_ANGLES,
    CAMERA_DISTANCES,
    COMPOSITIONS,
    LIGHTING_STYLES,
    apply_profile_to_prompt,
    assign_visual_profiles,
    profile_to_text,
)


SIX_SCENES = [
    {"scene": i, "narration": f"n{i}", "image_prompt": f"p{i}"}
    for i in range(1, 7)
]


class TestDimensionConstants(unittest.TestCase):
    """Sprint72-1 - 요구사항에 명시된 4개 차원과 정확히 일치해야 한다."""

    def test_camera_distances(self):
        self.assertEqual(
            CAMERA_DISTANCES, ["wide", "medium", "close-up", "macro"],
        )

    def test_camera_angles(self):
        self.assertEqual(
            CAMERA_ANGLES,
            ["eye level", "low angle", "high angle", "top-down", "side view", "over shoulder"],
        )

    def test_compositions(self):
        self.assertEqual(
            COMPOSITIONS,
            ["centered", "rule of thirds", "foreground framing", "leading lines"],
        )

    def test_lighting_styles(self):
        self.assertEqual(
            LIGHTING_STYLES,
            ["soft daylight", "dramatic light", "warm indoor", "cool ambient", "backlit"],
        )


class TestAssignVisualProfiles(unittest.TestCase):

    def test_empty_scenes_returns_empty_dict(self):
        self.assertEqual(assign_visual_profiles([]), {})

    def test_none_scenes_returns_empty_dict(self):
        self.assertEqual(assign_visual_profiles(None), {})

    def test_every_scene_gets_a_profile(self):
        profiles = assign_visual_profiles(SIX_SCENES)
        self.assertEqual(set(profiles.keys()), {1, 2, 3, 4, 5, 6})

    def test_profile_contains_all_four_dimensions(self):
        profiles = assign_visual_profiles(SIX_SCENES)
        for profile in profiles.values():
            self.assertIn(profile["camera_distance"], CAMERA_DISTANCES)
            self.assertIn(profile["camera_angle"], CAMERA_ANGLES)
            self.assertIn(profile["composition"], COMPOSITIONS)
            self.assertIn(profile["lighting"], LIGHTING_STYLES)

    def test_no_duplicate_distance_angle_combination_across_scenes(self):
        # 요구사항3 - 동일 영상에서 같은 Camera Angle/Distance 조합이
        # 반복되지 않아야 한다.
        profiles = assign_visual_profiles(SIX_SCENES)
        combos = [
            (p["camera_distance"], p["camera_angle"]) for p in profiles.values()
        ]
        self.assertEqual(len(combos), len(set(combos)))

    def test_does_not_mutate_input_scenes(self):
        scenes_copy = [dict(s) for s in SIX_SCENES]
        assign_visual_profiles(SIX_SCENES)
        self.assertEqual(SIX_SCENES, scenes_copy)

    def test_single_scene_still_gets_a_profile(self):
        profiles = assign_visual_profiles([{"scene": 1, "narration": "n", "image_prompt": "p"}])
        self.assertIn(1, profiles)

    def test_more_scenes_than_any_single_dimension_still_works(self):
        # 24개(4*6) 조합 상한 이내라면 예외 없이 계속 서로 다른 조합을
        # 배정해야 한다.
        many_scenes = [
            {"scene": i, "narration": f"n{i}", "image_prompt": f"p{i}"}
            for i in range(1, 13)
        ]
        profiles = assign_visual_profiles(many_scenes)
        combos = [
            (p["camera_distance"], p["camera_angle"]) for p in profiles.values()
        ]
        self.assertEqual(len(combos), len(set(combos)))


class TestProfileToText(unittest.TestCase):

    def test_contains_all_four_dimension_values(self):
        profile = {
            "camera_distance": "close-up",
            "camera_angle": "low angle",
            "composition": "rule of thirds",
            "lighting": "dramatic light",
        }
        text = profile_to_text(profile)

        self.assertIn("close-up", text)
        self.assertIn("low angle", text)
        self.assertIn("rule of thirds", text)
        self.assertIn("dramatic light", text)


class TestApplyProfileToPrompt(unittest.TestCase):

    def setUp(self):
        self.profile = {
            "camera_distance": "wide",
            "camera_angle": "high angle",
            "composition": "leading lines",
            "lighting": "backlit",
        }

    def test_appends_profile_text_to_prompt(self):
        result = apply_profile_to_prompt("A photo of a forest.", self.profile)

        self.assertTrue(result.startswith("A photo of a forest."))
        self.assertIn(profile_to_text(self.profile), result)

    def test_none_profile_returns_prompt_unchanged(self):
        self.assertEqual(
            apply_profile_to_prompt("A photo of a forest.", None),
            "A photo of a forest.",
        )

    def test_empty_prompt_returns_unchanged(self):
        self.assertEqual(apply_profile_to_prompt("", self.profile), "")
        self.assertIsNone(apply_profile_to_prompt(None, self.profile))

    def test_does_not_duplicate_already_present_profile_text(self):
        once = apply_profile_to_prompt("A photo of a forest.", self.profile)
        twice = apply_profile_to_prompt(once, self.profile)

        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
