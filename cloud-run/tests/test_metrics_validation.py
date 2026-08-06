"""
Sprint72 - Prompt Metrics Validation.

Stage 4(Prompt Optimization)는 prompt_metrics 점수를 목적함수로 삼는다.
그 전에 물어야 할 것이 있다 - 그 점수가 실제 영상 품질과 상관이 있는가.

Stage 3에서 이미 한 번 어긋난 적이 있다. Enrichment를 켜자 점수는
90 -> 100으로 올랐는데 실제 이미지는 나빠졌다. 루브릭이 "계획한 문구가
프롬프트에 들어갔는가"를 보기 때문에, 문구를 넣으면 정의상 점수가
오른다.

이 모듈은 그 상관을 실제 데이터로 잰다. 지금까지의 평가 실행이 남긴
measurements.json(프롬프트 점수)과 evaluation.json(Gemini 품질)을
scene 단위로 짝지어, 어떤 check가 품질을 예측하는지 본다.

통계는 stdlib만 쓴다. 상수 지표를 만나면 조용히 0을 내놓지 않고
"분산 없음"으로 표시한다 - 상관계수가 0인 것과 계산할 수 없는 것은
전혀 다른 이야기이고, 그 구분을 흐리면 "상관 없음"으로 오독된다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.tools import metrics_validation as mv


class TestPearson(unittest.TestCase):

    def test_perfect_positive_correlation(self):
        result = mv.pearson([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
        self.assertAlmostEqual(result, 1.0, places=9)

    def test_perfect_negative_correlation(self):
        result = mv.pearson([1, 2, 3, 4, 5], [50, 40, 30, 20, 10])
        self.assertAlmostEqual(result, -1.0, places=9)

    def test_no_correlation_is_near_zero(self):
        # 대칭이라 공분산이 정확히 0이 되는 쌍.
        result = mv.pearson([1, 2, 3, 4], [1, -1, -1, 1])
        self.assertAlmostEqual(result, 0.0, places=9)

    def test_a_constant_series_has_no_correlation_not_zero_correlation(self):
        # 이 구분이 이 Epic의 핵심이다. 분산이 없으면 상관계수는
        # 0이 아니라 정의되지 않는다.
        self.assertIsNone(mv.pearson([5, 5, 5, 5], [1, 2, 3, 4]))
        self.assertIsNone(mv.pearson([1, 2, 3, 4], [7, 7, 7, 7]))

    def test_too_few_points_returns_none(self):
        self.assertIsNone(mv.pearson([1], [2]))
        self.assertIsNone(mv.pearson([], []))

    def test_mismatched_lengths_are_rejected(self):
        with self.assertRaises(ValueError):
            mv.pearson([1, 2, 3], [1, 2])


class TestSpearman(unittest.TestCase):

    def test_monotonic_but_nonlinear_gets_a_perfect_rank_correlation(self):
        # 순위만 보므로 곡선이어도 1.0이다 - Gemini 점수처럼 눈금이
        # 고르지 않은 값에는 이쪽이 더 정직하다.
        result = mv.spearman([1, 2, 3, 4], [1, 4, 9, 16])
        self.assertAlmostEqual(result, 1.0, places=9)

    def test_ties_are_averaged_not_dropped(self):
        result = mv.spearman([1, 1, 2, 2], [10, 20, 30, 40])
        self.assertIsNotNone(result)

    def test_a_constant_series_returns_none(self):
        self.assertIsNone(mv.spearman([3, 3, 3], [1, 2, 3]))


class TestDescribeSeries(unittest.TestCase):

    def test_a_varying_series_is_reported_as_varying(self):
        described = mv.describe_series([1, 2, 3])

        self.assertTrue(described["varies"])
        self.assertEqual(described["distinct"], 3)

    def test_a_constant_series_is_flagged(self):
        described = mv.describe_series([True] * 10)

        self.assertFalse(described["varies"])
        self.assertEqual(described["distinct"], 1)

    def test_booleans_are_summarised_as_a_pass_rate(self):
        described = mv.describe_series([True, True, False, True])

        self.assertAlmostEqual(described["mean"], 0.75)


class TestGroupComparison(unittest.TestCase):
    """불리언 check는 상관계수보다 "통과한 쪽과 실패한 쪽의 품질 차이"로
    보는 편이 읽기 쉽다."""

    def test_reports_both_group_means_and_the_gap(self):
        flags = [True, True, False, False]
        quality = [90, 80, 40, 30]

        result = mv.compare_groups(flags, quality)

        self.assertAlmostEqual(result["passed_mean"], 85.0)
        self.assertAlmostEqual(result["failed_mean"], 35.0)
        self.assertAlmostEqual(result["gap"], 50.0)

    def test_a_constant_flag_cannot_be_compared(self):
        result = mv.compare_groups([True] * 6, [10, 20, 30, 40, 50, 60])

        self.assertIsNone(result["gap"])
        self.assertFalse(result["comparable"])

    def test_a_comparable_flag_gets_a_p_value(self):
        result = mv.compare_groups(
            [True, True, True, False, False, False],
            [90, 92, 88, 20, 25, 22],
        )

        self.assertTrue(result["comparable"])
        self.assertLessEqual(result["p_value"], 0.05)


class TestCorrelate(unittest.TestCase):

    OBSERVATIONS = [
        {"length": 100, "keywords": 0, "score": 90, "realism": 30},
        {"length": 200, "keywords": 0, "score": 90, "realism": 50},
        {"length": 300, "keywords": 0, "score": 90, "realism": 70},
        {"length": 400, "keywords": 0, "score": 90, "realism": 90},
    ]

    def test_every_requested_feature_is_reported(self):
        result = mv.correlate(
            self.OBSERVATIONS, features=("length", "keywords", "score"),
            target="realism",
        )

        self.assertEqual(
            set(result), {"length", "keywords", "score"},
        )

    def test_a_predictive_feature_shows_a_strong_correlation(self):
        result = mv.correlate(
            self.OBSERVATIONS, features=("length",), target="realism",
        )

        self.assertAlmostEqual(result["length"]["pearson"], 1.0, places=9)

    def test_a_constant_feature_reports_no_variance_rather_than_zero(self):
        result = mv.correlate(
            self.OBSERVATIONS, features=("keywords", "score"),
            target="realism",
        )

        for name in ("keywords", "score"):
            with self.subTest(feature=name):
                self.assertIsNone(result[name]["pearson"])
                self.assertFalse(result[name]["varies"])

    def test_an_empty_dataset_is_rejected(self):
        with self.assertRaises(ValueError):
            mv.correlate([], features=("length",), target="realism")


class TestObjectiveRecommendation(unittest.TestCase):
    """분석 결과를 "무엇을 목적함수로 쓸 수 있는가"로 옮긴다."""

    def test_a_rubric_with_no_varying_checks_is_rejected(self):
        analysis = {
            "prompt_preserved": {"varies": False, "pearson": None},
            "camera": {"varies": False, "pearson": None},
        }

        verdict = mv.recommend_objective(analysis)

        self.assertFalse(verdict["usable"])
        self.assertIn("변동", verdict["reason"])

    def test_a_check_that_varies_but_does_not_predict_is_not_usable(self):
        analysis = {
            "length": {"varies": True, "pearson": 0.02, "spearman": 0.01},
        }

        verdict = mv.recommend_objective(analysis)

        self.assertFalse(verdict["usable"])

    def test_a_predictive_check_is_recommended(self):
        analysis = {
            "length": {"varies": True, "pearson": 0.62, "spearman": 0.58},
            "camera": {"varies": False, "pearson": None},
        }

        verdict = mv.recommend_objective(analysis)

        self.assertTrue(verdict["usable"])
        self.assertIn("length", verdict["predictors"])
        self.assertNotIn("camera", verdict["predictors"])


if __name__ == "__main__":
    unittest.main()
