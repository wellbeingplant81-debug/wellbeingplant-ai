"""
Sprint106 - Distribution Analytics Intelligence. distribution_analytics.py의
compute_analytics()는 asset_feedback_service.summarize_usage()와 동일한
패턴의 순수 함수다 - queue_entries/history_records 리스트를 받아 통계
dict를 반환할 뿐, 파일 I/O를 전혀 하지 않는다(distribution_store.
list_entries()/distribution_history.load_all()의 반환값을 그대로
입력으로 받는 형태).

출력 schema는 SPEC §3에서 고정:
- rate는 0~1 float(퍼센트 변환 안 함)
- 빈 그룹은 0이 아니라 null(None)
- platform_success_rate는 history_records 기준 attempt 단위(재시도도 포함)
- retry_stats/quality_correlation은 queue_entries의 publish_result 존재
  여부로 대상을 거른다(아직 발행 시도 자체가 없는 항목은 제외)
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import distribution_analytics


def _queue_entry(video_id, status="waiting_review", retry_count=0,
                  publish_result=None, quality_score=None, generation_time=None):
    return {
        "video_id": video_id,
        "status": status,
        "retry_count": retry_count,
        "publish_result": publish_result,
        "quality_score": quality_score,
        "generation_time": generation_time,
    }


def _history_record(video_id, platform, success):
    return {
        "video_id": video_id,
        "platform": platform,
        "success": success,
        "platform_post_id": "id" if success else None,
        "error": None if success else "boom",
        "retry_count": 0,
        "published_at": "2026-07-16T00:00:00+00:00",
    }


class TestComputeAnalyticsEmptyInput(unittest.TestCase):

    def test_empty_input_returns_full_structure_with_nulls(self):
        result = distribution_analytics.compute_analytics([], [])

        self.assertEqual(result["platform_success_rate"], {})
        self.assertEqual(result["retry_stats"]["eligible_entries"], 0)
        self.assertIsNone(result["retry_stats"]["average_retry_count"])
        self.assertIsNone(result["retry_stats"]["success_rate_without_retry"])
        self.assertIsNone(result["retry_stats"]["success_rate_after_retry"])
        self.assertEqual(result["quality_correlation"]["eligible_entries"], 0)
        self.assertEqual(result["quality_correlation"]["published"]["count"], 0)
        self.assertIsNone(result["quality_correlation"]["published"]["avg_quality_score"])
        self.assertEqual(result["quality_correlation"]["failed"]["count"], 0)

    def test_does_not_raise_on_empty_input(self):
        # 예외 없이 위 구조를 반환해야 한다(asset_feedback_service.
        # summarize_usage()의 total==0 처리와 동일 원칙).
        try:
            distribution_analytics.compute_analytics([], [])
        except Exception as exc:
            self.fail(f"compute_analytics([], []) raised {exc!r}")


class TestPlatformSuccessRate(unittest.TestCase):

    def test_single_platform_all_success(self):
        history = [
            _history_record("v1", "youtube", True),
            _history_record("v2", "youtube", True),
        ]
        result = distribution_analytics.compute_analytics([], history)

        self.assertEqual(
            result["platform_success_rate"]["youtube"],
            {"attempts": 2, "successes": 2, "rate": 1.0},
        )

    def test_rate_is_float_0_to_1_not_percentage(self):
        history = [
            _history_record("v1", "youtube", True),
            _history_record("v1", "youtube", False),
            _history_record("v1", "youtube", False),
            _history_record("v1", "youtube", False),
        ]
        result = distribution_analytics.compute_analytics([], history)

        rate = result["platform_success_rate"]["youtube"]["rate"]
        self.assertEqual(rate, 0.25)
        self.assertLessEqual(rate, 1.0)
        self.assertGreaterEqual(rate, 0.0)

    def test_multiple_platforms_computed_independently(self):
        history = [
            _history_record("v1", "youtube", True),
            _history_record("v1", "instagram", False),
            _history_record("v2", "instagram", True),
        ]
        result = distribution_analytics.compute_analytics([], history)

        self.assertEqual(result["platform_success_rate"]["youtube"]["rate"], 1.0)
        self.assertEqual(result["platform_success_rate"]["instagram"]["rate"], 0.5)

    def test_retry_attempts_are_all_counted_not_just_latest(self):
        # 같은 video_id/platform이 재시도로 3번 등장하면 attempts=3으로
        # 전부 잡힌다(최신 시도 하나만 보는 게 아님).
        history = [
            _history_record("v1", "youtube", False),
            _history_record("v1", "youtube", False),
            _history_record("v1", "youtube", True),
        ]
        result = distribution_analytics.compute_analytics([], history)

        self.assertEqual(
            result["platform_success_rate"]["youtube"],
            {"attempts": 3, "successes": 1, "rate": 1 / 3},
        )

    def test_platform_absent_from_history_not_included(self):
        history = [_history_record("v1", "youtube", True)]
        result = distribution_analytics.compute_analytics([], history)

        self.assertNotIn("tiktok", result["platform_success_rate"])


class TestRetryStats(unittest.TestCase):

    def test_entries_without_publish_attempt_excluded(self):
        entries = [
            _queue_entry("v1", status="waiting_review", publish_result=None),
            _queue_entry("v2", status="approved", publish_result=None),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        self.assertEqual(result["retry_stats"]["eligible_entries"], 0)
        self.assertIsNone(result["retry_stats"]["average_retry_count"])

    def test_average_retry_count(self):
        entries = [
            _queue_entry("v1", status="published", retry_count=0, publish_result={}),
            _queue_entry("v2", status="published", retry_count=2, publish_result={}),
            _queue_entry("v3", status="failed", retry_count=1, publish_result={}),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        self.assertEqual(result["retry_stats"]["eligible_entries"], 3)
        self.assertAlmostEqual(result["retry_stats"]["average_retry_count"], 1.0)

    def test_success_rate_without_retry(self):
        entries = [
            _queue_entry("v1", status="published", retry_count=0, publish_result={}),
            _queue_entry("v2", status="published", retry_count=0, publish_result={}),
            _queue_entry("v3", status="failed", retry_count=0, publish_result={}),
            _queue_entry("v4", status="failed", retry_count=0, publish_result={}),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        self.assertEqual(result["retry_stats"]["success_rate_without_retry"], 0.5)

    def test_success_rate_after_retry(self):
        entries = [
            _queue_entry("v1", status="published", retry_count=1, publish_result={}),
            _queue_entry("v2", status="published", retry_count=2, publish_result={}),
            _queue_entry("v3", status="failed", retry_count=1, publish_result={}),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        self.assertAlmostEqual(
            result["retry_stats"]["success_rate_after_retry"], 2 / 3,
        )

    def test_without_retry_group_null_when_empty(self):
        entries = [
            _queue_entry("v1", status="published", retry_count=1, publish_result={}),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        self.assertIsNone(result["retry_stats"]["success_rate_without_retry"])
        self.assertIsNotNone(result["retry_stats"]["success_rate_after_retry"])

    def test_after_retry_group_null_when_empty(self):
        entries = [
            _queue_entry("v1", status="published", retry_count=0, publish_result={}),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        self.assertIsNone(result["retry_stats"]["success_rate_after_retry"])
        self.assertIsNotNone(result["retry_stats"]["success_rate_without_retry"])


class TestQualityCorrelation(unittest.TestCase):

    def test_entries_without_quality_score_excluded(self):
        entries = [
            _queue_entry(
                "v1", status="published", publish_result={}, quality_score=None,
            ),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        self.assertEqual(result["quality_correlation"]["eligible_entries"], 0)

    def test_entries_without_publish_attempt_excluded(self):
        entries = [
            _queue_entry(
                "v1", status="waiting_review", publish_result=None, quality_score=0.9,
            ),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        self.assertEqual(result["quality_correlation"]["eligible_entries"], 0)

    def test_averages_computed_per_status_group(self):
        entries = [
            _queue_entry(
                "v1", status="published", publish_result={},
                quality_score=0.9, generation_time=100.0,
            ),
            _queue_entry(
                "v2", status="published", publish_result={},
                quality_score=0.8, generation_time=120.0,
            ),
            _queue_entry(
                "v3", status="failed", publish_result={},
                quality_score=0.5, generation_time=200.0,
            ),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        published = result["quality_correlation"]["published"]
        failed = result["quality_correlation"]["failed"]

        self.assertEqual(published["count"], 2)
        self.assertAlmostEqual(published["avg_quality_score"], 0.85)
        self.assertAlmostEqual(published["avg_generation_time"], 110.0)

        self.assertEqual(failed["count"], 1)
        self.assertAlmostEqual(failed["avg_quality_score"], 0.5)
        self.assertAlmostEqual(failed["avg_generation_time"], 200.0)

    def test_generation_time_none_excluded_from_avg_but_counted(self):
        entries = [
            _queue_entry(
                "v1", status="published", publish_result={},
                quality_score=0.9, generation_time=None,
            ),
            _queue_entry(
                "v2", status="published", publish_result={},
                quality_score=0.7, generation_time=140.0,
            ),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        published = result["quality_correlation"]["published"]
        self.assertEqual(published["count"], 2)
        self.assertAlmostEqual(published["avg_quality_score"], 0.8)
        self.assertAlmostEqual(published["avg_generation_time"], 140.0)

    def test_group_null_when_empty(self):
        entries = [
            _queue_entry(
                "v1", status="published", publish_result={}, quality_score=0.9,
            ),
        ]
        result = distribution_analytics.compute_analytics(entries, [])

        failed = result["quality_correlation"]["failed"]
        self.assertEqual(failed["count"], 0)
        self.assertIsNone(failed["avg_quality_score"])
        self.assertIsNone(failed["avg_generation_time"])


class TestComputeAnalyticsIsPure(unittest.TestCase):

    def test_does_not_mutate_inputs(self):
        entries = [
            _queue_entry(
                "v1", status="published", retry_count=1, publish_result={"a": 1},
                quality_score=0.9, generation_time=100.0,
            ),
        ]
        history = [_history_record("v1", "youtube", True)]

        entries_snapshot = [dict(e) for e in entries]
        history_snapshot = [dict(h) for h in history]

        distribution_analytics.compute_analytics(entries, history)

        self.assertEqual(entries, entries_snapshot)
        self.assertEqual(history, history_snapshot)


if __name__ == "__main__":
    unittest.main()
