"""
Sprint107 - Distribution Decision Intelligence. SPEC 확정 완료.

compute_decision()은 distribution_analytics.compute_analytics()의
출력(dict)을 입력으로 받는 순수 함수다 - Sprint106 analytics 계층 위에
한 단계 더 쌓는 구조(analytics_data -> decision). 파일 I/O 없음.

확정된 규칙:
- score = platform_success_rate[platform]["rate"] 그대로
- attempts < 5 인 플랫폼은 threshold 판정 대신 status="insufficient_data"
  (score는 그대로 rate를 담되 신뢰도가 낮다는 뜻)
- threshold(attempts>=5일 때만 적용): >=0.8 healthy, 0.5~0.8 degraded, <0.5 critical
- recommendation: degraded/critical 플랫폼당 pattern="low_success_rate" 1건
  (insufficient_data 플랫폼은 recommendation 생성 안 함 - 판단할 데이터가
  부족하다는 뜻이지 실패 패턴이 확인된 게 아니므로)
- overall_status 우선순위: critical > degraded > healthy > insufficient_data
  (platform_health가 아예 비어 있어도 insufficient_data)
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import distribution_decision


def _analytics(platform_success_rate=None, retry_stats=None, quality_correlation=None):
    """compute_analytics()가 실제로 반환하는 것과 동일한 shape을 만든다."""
    return {
        "platform_success_rate": platform_success_rate or {},
        "retry_stats": retry_stats or {
            "eligible_entries": 0,
            "average_retry_count": None,
            "success_rate_without_retry": None,
            "success_rate_after_retry": None,
        },
        "quality_correlation": quality_correlation or {
            "eligible_entries": 0,
            "published": {"count": 0, "avg_quality_score": None, "avg_generation_time": None},
            "failed": {"count": 0, "avg_quality_score": None, "avg_generation_time": None},
        },
    }


class TestComputeDecisionFromAnalytics(unittest.TestCase):
    """검증 항목 1 - analytics 데이터 기반 decision 생성."""

    def test_returns_three_top_level_sections(self):
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 10, "successes": 9, "rate": 0.9}},
        )
        result = distribution_decision.compute_decision(analytics)

        for key in ["platform_health", "recommendations", "overall_status"]:
            with self.subTest(key=key):
                self.assertIn(key, result)

    def test_does_not_mutate_input_analytics(self):
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 10, "successes": 9, "rate": 0.9}},
        )
        snapshot = {
            "platform_success_rate": dict(analytics["platform_success_rate"]),
            "retry_stats": dict(analytics["retry_stats"]),
            "quality_correlation": dict(analytics["quality_correlation"]),
        }

        distribution_decision.compute_decision(analytics)

        self.assertEqual(analytics["platform_success_rate"], snapshot["platform_success_rate"])
        self.assertEqual(analytics["retry_stats"], snapshot["retry_stats"])
        self.assertEqual(analytics["quality_correlation"], snapshot["quality_correlation"])

    def test_does_not_raise_on_well_formed_analytics(self):
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 10, "successes": 9, "rate": 0.9},
                "tiktok": {"attempts": 4, "successes": 1, "rate": 0.25},
            },
        )
        try:
            distribution_decision.compute_decision(analytics)
        except Exception as exc:
            self.fail(f"compute_decision() raised {exc!r}")


class TestPlatformHealthScore(unittest.TestCase):
    """
    검증 항목 2 - platform health score 계산(attempts>=5 케이스만 -
    attempts<5 최소 표본 규칙은 TestInsufficientDataThreshold에서 다룬다).

    score == platform_success_rate[platform]["rate"] 그대로.
    임계값: >=0.8 healthy, 0.5~0.8 degraded, <0.5 critical.
    """

    def test_score_equals_success_rate(self):
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 20, "successes": 17, "rate": 0.85}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["youtube"]["score"], 0.85)

    def test_score_is_float_0_to_1_not_percentage(self):
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 8, "successes": 2, "rate": 0.25}},
        )
        result = distribution_decision.compute_decision(analytics)

        score = result["platform_health"]["youtube"]["score"]
        self.assertEqual(score, 0.25)
        self.assertLessEqual(score, 1.0)
        self.assertGreaterEqual(score, 0.0)

    def test_status_healthy_at_and_above_0_8(self):
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 10, "successes": 8, "rate": 0.8}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["youtube"]["status"], "healthy")

    def test_status_degraded_between_0_5_and_0_8(self):
        analytics = _analytics(
            platform_success_rate={"instagram": {"attempts": 10, "successes": 6, "rate": 0.6}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["instagram"]["status"], "degraded")

    def test_status_critical_below_0_5(self):
        analytics = _analytics(
            platform_success_rate={"tiktok": {"attempts": 10, "successes": 3, "rate": 0.3}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["tiktok"]["status"], "critical")

    def test_health_includes_attempts_for_context(self):
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 12, "successes": 12, "rate": 1.0}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["youtube"]["attempts"], 12)

    def test_multiple_platforms_scored_independently(self):
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 10, "successes": 9, "rate": 0.9},
                "instagram": {"attempts": 10, "successes": 6, "rate": 0.6},
                "tiktok": {"attempts": 10, "successes": 2, "rate": 0.2},
            },
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["youtube"]["status"], "healthy")
        self.assertEqual(result["platform_health"]["instagram"]["status"], "degraded")
        self.assertEqual(result["platform_health"]["tiktok"]["status"], "critical")


class TestFailurePatternRecommendation(unittest.TestCase):
    """
    검증 항목 3 - failure pattern recommendation.

    degraded/critical 플랫폼마다 recommendation 1건, healthy는 생성
    안 함. recommendation은 최소 platform/pattern/severity 필드를
    가진다. insufficient_data 케이스는 TestInsufficientDataThreshold에서.
    """

    def test_healthy_platform_produces_no_recommendation(self):
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 10, "successes": 10, "rate": 1.0}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["recommendations"], [])

    def test_critical_platform_produces_recommendation(self):
        analytics = _analytics(
            platform_success_rate={"tiktok": {"attempts": 8, "successes": 1, "rate": 0.125}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(len(result["recommendations"]), 1)
        rec = result["recommendations"][0]
        self.assertEqual(rec["platform"], "tiktok")
        self.assertEqual(rec["severity"], "critical")

    def test_degraded_platform_produces_recommendation(self):
        analytics = _analytics(
            platform_success_rate={"instagram": {"attempts": 10, "successes": 6, "rate": 0.6}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["recommendations"][0]["platform"], "instagram")
        self.assertEqual(result["recommendations"][0]["severity"], "degraded")

    def test_mixed_platforms_only_unhealthy_ones_get_recommendations(self):
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 10, "successes": 9, "rate": 0.9},
                "instagram": {"attempts": 10, "successes": 4, "rate": 0.4},
            },
        )
        result = distribution_decision.compute_decision(analytics)

        platforms_with_recs = {rec["platform"] for rec in result["recommendations"]}
        self.assertEqual(platforms_with_recs, {"instagram"})


class TestOverallStatus(unittest.TestCase):
    """
    데이터 없음 -> insufficient_data, 우선순위 critical > degraded >
    healthy. insufficient_data가 다른 상태와 섞이는 케이스는
    TestInsufficientDataThreshold에서.
    """

    def test_healthy_when_all_platforms_healthy(self):
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 10, "successes": 10, "rate": 1.0}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["overall_status"], "healthy")

    def test_critical_wins_over_degraded(self):
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 10, "successes": 6, "rate": 0.6},
                "tiktok": {"attempts": 10, "successes": 1, "rate": 0.1},
            },
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["overall_status"], "critical")

    def test_degraded_when_no_critical_present(self):
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 10, "successes": 9, "rate": 0.9},
                "instagram": {"attempts": 10, "successes": 6, "rate": 0.6},
            },
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["overall_status"], "degraded")


class TestInsufficientDataThreshold(unittest.TestCase):
    """
    SPEC 확정 - attempts < 5인 플랫폼은 threshold 판정을 건너뛰고
    status="insufficient_data"가 된다(score는 여전히 rate 그대로 담김 -
    "값이 없다"가 아니라 "신뢰도가 낮다"는 뜻). 5는 경계값 포함
    (attempts>=5부터 정상 threshold 적용).
    """

    def test_below_minimum_sample_is_insufficient_data_even_with_high_rate(self):
        # rate=1.0(완벽한 성공률)이어도 attempts=4면 healthy로 판정하지
        # 않는다 - 표본이 너무 적어 신뢰할 수 없다.
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 4, "successes": 4, "rate": 1.0}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["youtube"]["status"], "insufficient_data")

    def test_below_minimum_sample_score_still_reports_raw_rate(self):
        analytics = _analytics(
            platform_success_rate={"tiktok": {"attempts": 2, "successes": 2, "rate": 1.0}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["tiktok"]["score"], 1.0)
        self.assertEqual(result["platform_health"]["tiktok"]["status"], "insufficient_data")

    def test_exactly_five_attempts_uses_normal_threshold(self):
        # 경계값: attempts==5는 "< 5"에 해당하지 않으므로 정상 threshold
        # 적용(insufficient_data 아님).
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 5, "successes": 5, "rate": 1.0}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["youtube"]["status"], "healthy")

    def test_four_attempts_is_insufficient_five_is_not(self):
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 4, "successes": 0, "rate": 0.0},
                "instagram": {"attempts": 5, "successes": 0, "rate": 0.0},
            },
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["platform_health"]["youtube"]["status"], "insufficient_data")
        self.assertEqual(result["platform_health"]["instagram"]["status"], "critical")

    def test_insufficient_data_platform_produces_no_recommendation(self):
        # 표본 부족은 "실패 패턴이 확인됐다"는 뜻이 아니므로 rate가
        # 낮아도(0.0) recommendation을 만들지 않는다.
        analytics = _analytics(
            platform_success_rate={"tiktok": {"attempts": 3, "successes": 0, "rate": 0.0}},
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["recommendations"], [])

    def test_overall_status_critical_wins_over_insufficient_data(self):
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 3, "successes": 3, "rate": 1.0},
                "tiktok": {"attempts": 10, "successes": 1, "rate": 0.1},
            },
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["overall_status"], "critical")

    def test_overall_status_healthy_wins_over_insufficient_data(self):
        # healthy > insufficient_data - 표본이 부족한 플랫폼이 섞여
        # 있어도 나머지가 전부 healthy면 전체는 healthy.
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 10, "successes": 10, "rate": 1.0},
                "tiktok": {"attempts": 2, "successes": 2, "rate": 1.0},
            },
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["overall_status"], "healthy")

    def test_overall_status_insufficient_data_when_all_platforms_below_minimum(self):
        analytics = _analytics(
            platform_success_rate={
                "youtube": {"attempts": 3, "successes": 3, "rate": 1.0},
                "tiktok": {"attempts": 1, "successes": 0, "rate": 0.0},
            },
        )
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["overall_status"], "insufficient_data")


class TestEmptyDataHandling(unittest.TestCase):
    """검증 항목 4 - empty data 처리."""

    def test_empty_platform_success_rate_returns_insufficient_data(self):
        analytics = _analytics()
        result = distribution_decision.compute_decision(analytics)

        self.assertEqual(result["overall_status"], "insufficient_data")
        self.assertEqual(result["platform_health"], {})
        self.assertEqual(result["recommendations"], [])

    def test_does_not_raise_on_empty_analytics(self):
        analytics = _analytics()
        try:
            distribution_decision.compute_decision(analytics)
        except Exception as exc:
            self.fail(f"compute_decision() raised {exc!r} on empty analytics")

    def test_zero_attempt_platform_does_not_crash(self):
        # platform_success_rate에 attempts=0인 항목이 들어올 일은
        # 현재 compute_analytics() 설계상 없지만(§3-1: history_records에
        # 없는 플랫폼은 아예 포함 안 됨), 방어적으로 0으로 나누지
        # 않는지 확인한다.
        analytics = _analytics(
            platform_success_rate={"youtube": {"attempts": 0, "successes": 0, "rate": 0.0}},
        )
        try:
            distribution_decision.compute_decision(analytics)
        except ZeroDivisionError:
            self.fail("compute_decision() must not divide by zero on attempts=0")


if __name__ == "__main__":
    unittest.main()
