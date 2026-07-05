import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_learning_engine import (
    FAILURE_PENALTY,
    MAX_FALLBACK_BONUS,
    MAX_SUCCESS_BONUS,
    MIN_SAMPLE_SIZE_FOR_PENALTY,
    SUCCESS_BONUS_PER_EVENT,
    compute_bias,
    get_learned_bias,
)


class TestComputeBias(unittest.TestCase):

    def test_empty_records_returns_zero(self):
        self.assertEqual(compute_bias([], "pexels_image"), 0.0)

    def test_successful_provider_gets_positive_bias(self):
        records = [
            {"provider": "pexels_image", "outcome": "success"},
            {"provider": "pexels_image", "outcome": "success"},
        ]

        bias = compute_bias(records, "pexels_image")
        self.assertAlmostEqual(bias, 2 * SUCCESS_BONUS_PER_EVENT)

    def test_success_bonus_is_capped(self):
        records = [
            {"provider": "pexels_image", "outcome": "success"}
            for _ in range(100)
        ]

        bias = compute_bias(records, "pexels_image")
        self.assertAlmostEqual(bias, MAX_SUCCESS_BONUS)

    def test_ai_image_bias_based_on_fallback_events(self):
        records = [
            {"provider": "pexels_image", "outcome": "success"},
            {"provider": "ai_image", "outcome": "fallback"},
            {"provider": "ai_image", "outcome": "fallback"},
        ]

        bias = compute_bias(records, "ai_image")
        self.assertGreater(bias, 0.0)
        self.assertLessEqual(bias, MAX_FALLBACK_BONUS)

    def test_ai_image_bias_zero_when_no_fallback_events(self):
        records = [{"provider": "pexels_image", "outcome": "success"}]
        self.assertEqual(compute_bias(records, "ai_image"), 0.0)

    def test_repeated_failure_applies_penalty(self):
        # pixabay_image가 한 번도 success하지 못했는데 전체 이력은
        # MIN_SAMPLE_SIZE_FOR_PENALTY 이상 쌓인 경우
        records = (
            [{"provider": "pexels_image", "outcome": "success"}]
            * MIN_SAMPLE_SIZE_FOR_PENALTY
        )

        bias = compute_bias(records, "pixabay_image")
        self.assertAlmostEqual(bias, -FAILURE_PENALTY)

    def test_no_penalty_when_sample_size_too_small(self):
        records = [{"provider": "pexels_image", "outcome": "success"}]

        bias = compute_bias(records, "pixabay_image")
        self.assertEqual(bias, 0.0)

    def test_provider_with_no_records_at_all_is_neutral_until_penalty_threshold(self):
        # pixabay_video가 전혀 언급되지 않은 이력 - 표본이 충분치
        # 않으면 0.0
        records = [{"provider": "pexels_image", "outcome": "success"}] * 2

        self.assertEqual(compute_bias(records, "pixabay_video"), 0.0)


class TestGetLearnedBias(unittest.TestCase):

    @patch("app.services.asset_learning_engine.load_all")
    def test_delegates_to_compute_bias_with_loaded_records(self, mock_load_all):
        mock_load_all.return_value = [
            {"provider": "pexels_image", "outcome": "success"},
        ]

        bias = get_learned_bias("pexels_image")

        self.assertAlmostEqual(bias, SUCCESS_BONUS_PER_EVENT)
        mock_load_all.assert_called_once()

    @patch("app.services.asset_learning_engine.load_all", return_value=[])
    def test_zero_bias_when_no_feedback_exists(self, mock_load_all):
        self.assertEqual(get_learned_bias("ai_image"), 0.0)


if __name__ == "__main__":
    unittest.main()
