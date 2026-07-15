"""
Sprint105 - Distribution Workflow Intelligence. distribution_history.py는
발행 시도 전체 이력을 append-only로 기록하는 별도 파일
(distribution_history.json)이다. asset_feedback_service.py와 동일한
컨벤션(경로 파라미터 오버라이드, atomic_write_json, 파일 없음/손상 시
빈 리스트)을 그대로 따른다.

queue.json의 publish_result(최신 시도 스냅샷)와 달리, 이 모듈은
재시도해도 이전 기록을 덮어쓰지 않고 계속 쌓는다 - §8-2 결정에 따라
필드명은 "failure_reason"이 아니라 기존과 동일한 "error"를 쓴다.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import distribution_history


class TestDistributionHistory(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.history_path = os.path.join(self._tmp_dir.name, "distribution_history.json")

    def test_load_all_returns_empty_list_when_file_missing(self):
        self.assertEqual(
            distribution_history.load_all(history_path=self.history_path), [],
        )

    def test_record_persists_entry_to_disk(self):
        distribution_history.record(
            video_id="v1",
            platform="youtube",
            success=True,
            platform_post_id="mock_youtube_v1",
            error=None,
            retry_count=0,
            history_path=self.history_path,
        )

        records = distribution_history.load_all(history_path=self.history_path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["video_id"], "v1")
        self.assertEqual(records[0]["platform"], "youtube")
        self.assertTrue(records[0]["success"])
        self.assertEqual(records[0]["platform_post_id"], "mock_youtube_v1")
        self.assertIsNone(records[0]["error"])
        self.assertEqual(records[0]["retry_count"], 0)

    def test_record_uses_error_field_not_failure_reason(self):
        # §8-2 확정 - failure_reason 필드를 새로 만들지 않고 기존
        # error 필드명을 그대로 쓴다.
        entry = distribution_history.record(
            video_id="v1", platform="tiktok", success=False,
            platform_post_id=None, error="quota exceeded", retry_count=1,
            history_path=self.history_path,
        )

        self.assertEqual(entry["error"], "quota exceeded")
        self.assertNotIn("failure_reason", entry)

    def test_record_sets_published_at_timestamp(self):
        entry = distribution_history.record(
            video_id="v1", platform="youtube", success=True,
            platform_post_id="id", error=None, retry_count=0,
            history_path=self.history_path,
        )

        self.assertIn("published_at", entry)
        self.assertIsNotNone(entry["published_at"])

    def test_retries_append_instead_of_overwriting(self):
        # 같은 video_id/platform이라도 재시도마다 새 레코드가 쌓인다 -
        # queue.json의 publish_result처럼 덮어쓰지 않는다.
        distribution_history.record(
            video_id="v1", platform="youtube", success=False,
            platform_post_id=None, error="network error", retry_count=0,
            history_path=self.history_path,
        )
        distribution_history.record(
            video_id="v1", platform="youtube", success=True,
            platform_post_id="mock_youtube_v1", error=None, retry_count=1,
            history_path=self.history_path,
        )

        records = distribution_history.load_all(history_path=self.history_path)

        self.assertEqual(len(records), 2)
        self.assertFalse(records[0]["success"])
        self.assertTrue(records[1]["success"])

    def test_load_all_filters_by_video_id(self):
        distribution_history.record(
            video_id="v1", platform="youtube", success=True,
            platform_post_id="id1", error=None, retry_count=0,
            history_path=self.history_path,
        )
        distribution_history.record(
            video_id="v2", platform="youtube", success=True,
            platform_post_id="id2", error=None, retry_count=0,
            history_path=self.history_path,
        )

        v1_only = distribution_history.load_all(
            video_id="v1", history_path=self.history_path,
        )

        self.assertEqual(len(v1_only), 1)
        self.assertEqual(v1_only[0]["video_id"], "v1")

    def test_corrupted_file_treated_as_empty(self):
        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
        with open(self.history_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        self.assertEqual(
            distribution_history.load_all(history_path=self.history_path), [],
        )


if __name__ == "__main__":
    unittest.main()
