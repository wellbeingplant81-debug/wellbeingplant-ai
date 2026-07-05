import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.video_quality_engine import (
    WEIGHTS,
    _flow_smoothness_score,
    _provider_consistency_score,
    _subtitle_readability_score,
    _visual_diversity_score,
    evaluate_video_quality,
)


class TestSubtitleReadabilityScore(unittest.TestCase):

    def test_normal_narration_scores_one(self):
        scenes = [{"narration": "오늘은 좋은 날입니다."}]
        self.assertEqual(_subtitle_readability_score(scenes), 1.0)

    def test_no_narration_at_all_scores_one_by_convention(self):
        self.assertEqual(_subtitle_readability_score([]), 1.0)

    def test_unsplittable_oversized_piece_lowers_score(self):
        # 공백이 전혀 없는 매우 긴 문자열은 split_subtitle이 나눌 수
        # 없어 MAX_CHARS를 넘는 조각 하나를 그대로 반환한다.
        scenes = [{"narration": "가" * 40 + "."}]
        self.assertLess(_subtitle_readability_score(scenes), 1.0)


class TestProviderConsistencyScore(unittest.TestCase):

    def test_all_same_provider_scores_one(self):
        scenes = [{"provider": "ai_image"}, {"provider": "ai_image"}]
        self.assertEqual(_provider_consistency_score(scenes), 1.0)

    def test_mixed_providers_scores_fraction(self):
        scenes = [
            {"provider": "ai_image"},
            {"provider": "ai_image"},
            {"provider": "pexels_image"},
        ]
        self.assertAlmostEqual(_provider_consistency_score(scenes), 2 / 3)

    def test_no_providers_scores_zero(self):
        self.assertEqual(_provider_consistency_score([{}, {}]), 0.0)


class TestVisualDiversityScore(unittest.TestCase):

    def test_single_scene_scores_one(self):
        self.assertEqual(_visual_diversity_score([{"scene": 1}]), 1.0)

    def test_all_distinct_scenes_score_one(self):
        scenes = [
            {"scene": 1, "provider": "ai_image", "search_query": "a"},
            {"scene": 2, "provider": "pexels_image", "search_query": "b"},
        ]
        self.assertEqual(_visual_diversity_score(scenes), 1.0)

    def test_identical_consecutive_scenes_lower_score(self):
        scenes = [
            {"scene": 1, "provider": "ai_image", "search_query": "a"},
            {"scene": 2, "provider": "ai_image", "search_query": "a"},
        ]
        self.assertEqual(_visual_diversity_score(scenes), 0.0)


class TestFlowSmoothnessScore(unittest.TestCase):

    def test_no_pairs_scores_one(self):
        self.assertEqual(_flow_smoothness_score([]), 1.0)

    def test_uniform_continuity_scores_high(self):
        pairs = [{"continuity_score": 0.5}, {"continuity_score": 0.5}]
        self.assertEqual(_flow_smoothness_score(pairs), 1.0)

    def test_volatile_continuity_scores_lower(self):
        pairs = [{"continuity_score": 1.0}, {"continuity_score": 0.0}]
        self.assertLess(_flow_smoothness_score(pairs), 1.0)


class TestEvaluateVideoQuality(unittest.TestCase):

    def test_returns_overall_score_and_all_components(self):
        scenes = [
            {"scene": 1, "narration": "안녕하세요.", "provider": "ai_image", "search_query": "a b"},
            {"scene": 2, "narration": "반갑습니다.", "provider": "ai_image", "search_query": "b c"},
        ]

        result = evaluate_video_quality(scenes)

        self.assertIn("overall_score", result)
        self.assertEqual(set(result["components"].keys()), set(WEIGHTS.keys()))

    def test_overall_score_is_weighted_average_of_components(self):
        scenes = [
            {"scene": 1, "narration": "안녕하세요.", "provider": "ai_image", "search_query": "a b"},
            {"scene": 2, "narration": "반갑습니다.", "provider": "ai_image", "search_query": "b c"},
        ]

        result = evaluate_video_quality(scenes)

        expected = sum(
            result["components"][key] * weight
            for key, weight in WEIGHTS.items()
        )
        self.assertAlmostEqual(result["overall_score"], expected)

    def test_scenes_not_mutated(self):
        scenes = [
            {"scene": 1, "narration": "안녕하세요.", "provider": "ai_image", "search_query": "a"},
        ]
        scenes_copy = [dict(s) for s in scenes]

        evaluate_video_quality(scenes_copy)

        self.assertEqual(scenes_copy, scenes)


if __name__ == "__main__":
    unittest.main()
