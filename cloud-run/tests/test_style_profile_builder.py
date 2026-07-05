import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.color_mood_engine import build_color_mood
from app.services.style_profile_builder import (
    CINEMATIC_FEEL,
    MINIMAL_COMPOSITION,
    build_style_profile,
    style_profile_to_text,
)


class TestBuildStyleProfile(unittest.TestCase):

    def test_default_channel_is_wellbeing(self):
        self.assertEqual(build_style_profile()["channel"], "wellbeing")

    def test_custom_channel_is_preserved(self):
        self.assertEqual(build_style_profile("foodbeat")["channel"], "foodbeat")

    def test_profile_contains_expected_keys(self):
        profile = build_style_profile()
        self.assertEqual(
            set(profile.keys()), {"channel", "color_mood", "composition", "cinematic"},
        )

    def test_color_mood_matches_color_mood_engine(self):
        self.assertEqual(build_style_profile()["color_mood"], build_color_mood())

    def test_composition_and_cinematic_are_fixed_criteria(self):
        profile = build_style_profile()
        self.assertEqual(profile["composition"], MINIMAL_COMPOSITION)
        self.assertEqual(profile["cinematic"], CINEMATIC_FEEL)

    def test_two_calls_produce_the_same_profile(self):
        self.assertEqual(build_style_profile("wellbeing"), build_style_profile("wellbeing"))


class TestStyleProfileToText(unittest.TestCase):

    def test_joins_all_three_components(self):
        profile = build_style_profile()
        text = style_profile_to_text(profile)

        self.assertIn(profile["color_mood"], text)
        self.assertIn(profile["composition"], text)
        self.assertIn(profile["cinematic"], text)


if __name__ == "__main__":
    unittest.main()
