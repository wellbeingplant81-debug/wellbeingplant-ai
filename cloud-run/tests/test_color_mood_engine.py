import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.color_mood_engine import (
    NATURAL_MORNING_LIGHT,
    WARM_SOFT_CLEAN_WELLNESS,
    build_color_mood,
)


class TestBuildColorMood(unittest.TestCase):

    def test_contains_warm_soft_clean_wellness(self):
        self.assertIn(WARM_SOFT_CLEAN_WELLNESS, build_color_mood())

    def test_contains_natural_morning_light(self):
        self.assertIn(NATURAL_MORNING_LIGHT, build_color_mood())

    def test_is_deterministic(self):
        self.assertEqual(build_color_mood(), build_color_mood())

    def test_returns_string(self):
        self.assertIsInstance(build_color_mood(), str)


if __name__ == "__main__":
    unittest.main()
