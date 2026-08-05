"""
Sprint70 - Evaluation Framework v2.

Sprint69에서 실행 한 번짜리 A/B로는 아무것도 판정할 수 없다는 것이
실측으로 드러났다. 완전히 동일한 설정의 두 실행이 Gemini Vision 기준
overall_quality 40 vs 90으로 갈렸다 - Imagen이 매번 다른 그림을 그리기
때문이다. 그 잡음 폭이 프롬프트 변경이 낼 수 있는 어떤 효과보다 컸다.

이 모듈은 그 문제를 통계로 다룬다. arm마다 여러 번 생성해 분포를 만들고,
분포끼리 비교한다.

검정은 정확 순열검정(exact permutation test)을 쓴다. 두 arm의 점수를
한 통에 넣고 가능한 모든 분할을 열거해, 관측된 차이만큼 벌어지는 분할이
전체의 몇 퍼센트인지 센다. arm당 5개면 분할이 252가지뿐이라 전부
열거할 수 있다 - 정규성 가정도, 근사도, scipy도 필요 없다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.tools import evaluation


class TestSummarize(unittest.TestCase):

    def test_reports_count_mean_and_stdev(self):
        summary = evaluation.summarize([10, 20, 30, 40, 50])

        self.assertEqual(summary["count"], 5)
        self.assertAlmostEqual(summary["mean"], 30.0)
        self.assertAlmostEqual(summary["stdev"], 15.8113883, places=6)
        self.assertEqual(summary["min"], 10)
        self.assertEqual(summary["max"], 50)

    def test_trimmed_mean_drops_one_high_and_one_low(self):
        # 90은 명백한 이상치. 잘라내면 나머지 셋의 평균이 남는다.
        summary = evaluation.summarize([10, 20, 30, 40, 90])

        self.assertAlmostEqual(summary["mean"], 38.0)
        self.assertAlmostEqual(summary["trimmed_mean"], 30.0)

    def test_stdev_of_a_single_sample_is_zero_not_an_error(self):
        summary = evaluation.summarize([42])

        self.assertEqual(summary["count"], 1)
        self.assertAlmostEqual(summary["mean"], 42.0)
        self.assertAlmostEqual(summary["stdev"], 0.0)

    def test_trimmed_mean_falls_back_when_there_is_nothing_left_to_trim(self):
        # 2개짜리 표본에서 위아래를 하나씩 자르면 아무것도 안 남는다.
        # 그럴 땐 자르지 않은 평균을 쓴다 - 조용히 0을 반환하면 그게
        # 점수인지 결측인지 알 수 없다.
        summary = evaluation.summarize([10, 20])

        self.assertAlmostEqual(summary["trimmed_mean"], 15.0)

    def test_empty_sample_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluation.summarize([])


class TestPermutationTest(unittest.TestCase):

    def test_identical_arms_are_not_significant(self):
        p = evaluation.permutation_p_value(
            [50, 50, 50, 50, 50], [50, 50, 50, 50, 50],
        )
        self.assertAlmostEqual(p, 1.0)

    def test_a_clean_separation_reaches_the_smallest_possible_p(self):
        # 후보가 전부 기준선보다 높으면 관측된 분할이 유일한 극단이다.
        # 5 vs 5의 분할은 252가지이므로 p의 하한은 1/252이다.
        p = evaluation.permutation_p_value(
            [10, 11, 12, 13, 14], [90, 91, 92, 93, 94],
        )
        self.assertAlmostEqual(p, 1 / 252, places=6)

    def test_a_candidate_that_is_worse_gets_p_near_one(self):
        p = evaluation.permutation_p_value(
            [90, 91, 92, 93, 94], [10, 11, 12, 13, 14],
        )
        self.assertGreater(p, 0.9)

    def test_the_test_is_one_sided(self):
        better = evaluation.permutation_p_value(
            [10, 20, 30], [40, 50, 60],
        )
        worse = evaluation.permutation_p_value(
            [40, 50, 60], [10, 20, 30],
        )
        self.assertLess(better, worse)

    def test_noise_of_the_size_we_actually_measured_is_not_significant(self):
        # Sprint69에서 동일 설정 두 실행이 40 vs 90이었다. 그 정도로
        # 흔들리는 분포끼리는 5회씩 돌려도 유의하지 않아야 한다 -
        # 유의하다고 나오면 이 프레임워크가 잡음을 신호로 읽는 것이다.
        baseline = [40, 90, 55, 75, 60]
        candidate = [45, 85, 60, 70, 65]

        p = evaluation.permutation_p_value(baseline, candidate)

        self.assertGreater(p, evaluation.SIGNIFICANCE_LEVEL)

    def test_mismatched_arm_sizes_are_allowed(self):
        p = evaluation.permutation_p_value([10, 20], [30, 40, 50])
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)

    def test_too_many_permutations_is_refused_rather_than_approximated(self):
        big = list(range(30))
        with self.assertRaises(ValueError):
            evaluation.permutation_p_value(big, big)

    def test_empty_arm_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluation.permutation_p_value([], [1, 2, 3])


class TestCompareArms(unittest.TestCase):

    BASELINE = {
        "overall_quality": [40, 45, 42, 38, 44],
        "image_realism": [50, 55, 52, 48, 54],
        "composition": [60, 62, 61, 59, 63],
        "hook_strength": [70, 72, 71, 69, 73],
    }

    STRONGER = {
        "overall_quality": [80, 85, 82, 78, 84],
        "image_realism": [70, 75, 72, 68, 74],
        "composition": [70, 72, 71, 69, 73],
        "hook_strength": [75, 77, 76, 74, 78],
    }

    def test_every_metric_gets_both_summaries_and_a_p_value(self):
        result = evaluation.compare_arms(self.BASELINE, self.STRONGER)

        for metric in self.BASELINE:
            entry = result["metrics"][metric]
            self.assertIn("baseline", entry)
            self.assertIn("candidate", entry)
            self.assertIn("p_value", entry)
            self.assertIn("delta_mean", entry)
            self.assertIn("delta_trimmed_mean", entry)

    def test_delta_is_candidate_minus_baseline(self):
        result = evaluation.compare_arms(self.BASELINE, self.STRONGER)
        entry = result["metrics"]["overall_quality"]

        self.assertAlmostEqual(
            entry["delta_mean"],
            entry["candidate"]["mean"] - entry["baseline"]["mean"],
        )

    def test_metrics_present_in_only_one_arm_are_reported_not_silently_dropped(self):
        candidate = dict(self.STRONGER)
        candidate["new_metric"] = [1, 2, 3, 4, 5]

        result = evaluation.compare_arms(self.BASELINE, candidate)

        self.assertIn("new_metric", result["unpaired_metrics"])
        self.assertNotIn("new_metric", result["metrics"])


class TestDecision(unittest.TestCase):

    def _arms(self, overall_baseline, overall_candidate, **guardrails):
        baseline = {
            "overall_quality": overall_baseline,
            "image_realism": guardrails.get("realism_b", [50] * 5),
            "composition": guardrails.get("composition_b", [50] * 5),
            "hook_strength": guardrails.get("hook_b", [50] * 5),
        }
        candidate = {
            "overall_quality": overall_candidate,
            "image_realism": guardrails.get("realism_c", [50] * 5),
            "composition": guardrails.get("composition_c", [50] * 5),
            "hook_strength": guardrails.get("hook_c", [50] * 5),
        }
        return baseline, candidate

    def test_a_clearly_better_candidate_is_approved(self):
        baseline, candidate = self._arms(
            [40, 42, 41, 39, 43], [80, 82, 81, 79, 83],
        )

        decision = evaluation.decide(
            evaluation.compare_arms(baseline, candidate)
        )

        self.assertTrue(decision["approved"])
        self.assertEqual(decision["verdict"], evaluation.VERDICT_ENABLE)

    def test_an_equal_candidate_is_rejected(self):
        baseline, candidate = self._arms(
            [40, 90, 55, 75, 60], [45, 85, 60, 70, 65],
        )

        decision = evaluation.decide(
            evaluation.compare_arms(baseline, candidate)
        )

        self.assertFalse(decision["approved"])
        self.assertEqual(decision["verdict"], evaluation.VERDICT_KEEP_DISABLED)

    def test_a_worse_candidate_is_rejected(self):
        baseline, candidate = self._arms(
            [80, 82, 81, 79, 83], [40, 42, 41, 39, 43],
        )

        decision = evaluation.decide(
            evaluation.compare_arms(baseline, candidate)
        )

        self.assertFalse(decision["approved"])

    def test_a_guardrail_regression_blocks_an_otherwise_winning_candidate(self):
        # 주지표는 확실히 좋아졌지만 구도가 확실히 나빠졌다면 통과시키지
        # 않는다 - 한 지표를 올리려고 다른 지표를 깎는 변경을 막는다.
        baseline, candidate = self._arms(
            [40, 42, 41, 39, 43], [80, 82, 81, 79, 83],
            composition_b=[80, 82, 81, 79, 83],
            composition_c=[40, 42, 41, 39, 43],
        )

        decision = evaluation.decide(
            evaluation.compare_arms(baseline, candidate)
        )

        self.assertFalse(decision["approved"])
        self.assertIn("composition", decision["blocking_metrics"])

    def test_a_significant_mean_with_a_worse_trimmed_mean_is_rejected(self):
        # 이상치 하나가 평균을 끌어올린 경우. 절사평균이 따라오지
        # 않으면 승인하지 않는다.
        baseline = {
            "overall_quality": [50, 50, 50, 50, 50],
            "image_realism": [50] * 5,
            "composition": [50] * 5,
            "hook_strength": [50] * 5,
        }
        candidate = {
            "overall_quality": [49, 49, 49, 49, 100],
            "image_realism": [50] * 5,
            "composition": [50] * 5,
            "hook_strength": [50] * 5,
        }

        decision = evaluation.decide(
            evaluation.compare_arms(baseline, candidate)
        )

        self.assertFalse(decision["approved"])

    def test_the_decision_explains_itself(self):
        baseline, candidate = self._arms(
            [40, 90, 55, 75, 60], [45, 85, 60, 70, 65],
        )

        decision = evaluation.decide(
            evaluation.compare_arms(baseline, candidate)
        )

        self.assertTrue(decision["reason"])
        self.assertIsInstance(decision["reason"], str)


class TestReport(unittest.TestCase):

    BASELINE = {"overall_quality": [40, 45, 42, 38, 44]}
    CANDIDATE = {"overall_quality": [80, 85, 82, 78, 84]}

    def test_report_contains_every_run_score(self):
        comparison = evaluation.compare_arms(self.BASELINE, self.CANDIDATE)
        report = evaluation.render_report(
            comparison, evaluation.decide(comparison),
            baseline_label="baseline", candidate_label="planner-v2",
        )

        for score in self.BASELINE["overall_quality"]:
            self.assertIn(str(score), report)
        for score in self.CANDIDATE["overall_quality"]:
            self.assertIn(str(score), report)

    def test_report_states_the_verdict_and_the_labels(self):
        comparison = evaluation.compare_arms(self.BASELINE, self.CANDIDATE)
        decision = evaluation.decide(comparison)
        report = evaluation.render_report(
            comparison, decision,
            baseline_label="baseline", candidate_label="planner-v2",
        )

        self.assertIn("planner-v2", report)
        self.assertIn(decision["verdict"], report)

    def test_report_is_markdown_a_human_can_read(self):
        comparison = evaluation.compare_arms(self.BASELINE, self.CANDIDATE)
        report = evaluation.render_report(
            comparison, evaluation.decide(comparison),
            baseline_label="baseline", candidate_label="planner-v2",
        )

        self.assertTrue(report.lstrip().startswith("#"))
        self.assertIn("|", report)


class TestCollectScores(unittest.TestCase):
    """생성 루프는 실제 API를 부르지만, 점수를 모아 정리하는 부분은
    주입된 평가 결과만으로 검증할 수 있어야 한다."""

    def test_scores_are_grouped_by_metric_across_runs(self):
        evaluations = [
            {"scores": {"overall_quality": 40, "composition": 60}},
            {"scores": {"overall_quality": 50, "composition": 70}},
            {"scores": {"overall_quality": 45, "composition": 65}},
        ]

        collected = evaluation.collect_scores(evaluations)

        self.assertEqual(collected["overall_quality"], [40, 50, 45])
        self.assertEqual(collected["composition"], [60, 70, 65])

    def test_a_failed_run_is_skipped_without_shifting_the_others(self):
        evaluations = [
            {"scores": {"overall_quality": 40}},
            None,
            {"scores": {"overall_quality": 50}},
        ]

        collected = evaluation.collect_scores(evaluations)

        self.assertEqual(collected["overall_quality"], [40, 50])

    def test_a_metric_missing_from_one_run_does_not_corrupt_the_series(self):
        evaluations = [
            {"scores": {"overall_quality": 40, "composition": 60}},
            {"scores": {"overall_quality": 50}},
        ]

        collected = evaluation.collect_scores(evaluations)

        self.assertEqual(collected["overall_quality"], [40, 50])
        self.assertEqual(collected["composition"], [60])


if __name__ == "__main__":
    unittest.main()
