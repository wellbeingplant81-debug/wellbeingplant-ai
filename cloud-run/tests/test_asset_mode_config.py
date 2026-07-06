import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_mode_config


class TestAssetModeConfig(unittest.TestCase):

    def setUp(self):
        self._env_patcher = patch.dict(os.environ, {}, clear=False)
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        os.environ.pop("ASSET_MODE", None)

    def test_no_env_var_defaults_to_balanced(self):
        self.assertEqual(asset_mode_config.get_asset_mode(), "balanced")

    def test_env_var_is_case_insensitive(self):
        os.environ["ASSET_MODE"] = "PREMIUM"
        self.assertEqual(asset_mode_config.get_asset_mode(), "premium")

    def test_unknown_mode_falls_back_to_balanced(self):
        os.environ["ASSET_MODE"] = "not_a_real_mode"
        self.assertEqual(asset_mode_config.get_asset_mode(), "balanced")

    def test_low_cost_has_smallest_ai_ratio_and_lowest_quality_bar(self):
        self.assertEqual(asset_mode_config.get_ai_ratio_cap("low_cost"), 0.20)
        self.assertEqual(
            asset_mode_config.get_pexels_quality_threshold("low_cost"), 0.85,
        )

    def test_balanced_is_the_documented_default_ratios(self):
        self.assertEqual(asset_mode_config.get_ai_ratio_cap("balanced"), 0.30)
        self.assertEqual(
            asset_mode_config.get_pexels_quality_threshold("balanced"), 0.90,
        )

    def test_premium_has_largest_ai_ratio_and_highest_quality_bar(self):
        self.assertEqual(asset_mode_config.get_ai_ratio_cap("premium"), 0.60)
        self.assertEqual(
            asset_mode_config.get_pexels_quality_threshold("premium"), 0.95,
        )

    def test_ratio_cap_reads_env_var_when_mode_not_passed_explicitly(self):
        os.environ["ASSET_MODE"] = "premium"
        self.assertEqual(asset_mode_config.get_ai_ratio_cap(), 0.60)

    def test_invalid_explicit_mode_falls_back_to_balanced(self):
        self.assertEqual(
            asset_mode_config.get_ai_ratio_cap("bogus_mode"),
            asset_mode_config.get_ai_ratio_cap("balanced"),
        )


if __name__ == "__main__":
    unittest.main()
