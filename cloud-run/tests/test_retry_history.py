"""
Sprint114 - Distribution Retry History Intelligence. RetryHistory +
to_retry_history() 변환 + RetryHistoryStore(InMemory) 계약 테스트.

RetryHistoryStore는 Sprint113 RetryExecution 결과를 InMemory로만
저장/조회한다 - DB/Queue/Scheduler에 전혀 연결하지 않는다(파일 I/O도
없음). Sprint105 distribution_history.py(파일 기반 발행 이력)와는
독립적인 계층이다. retry_executor.py/retry_policy.py/upload 계층은
이 스프린트에서 수정하지 않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.retry_execution import RetryExecution
from app.models.retry_history import RetryHistory
from app.models.upload_execution import UploadExecution, UploadStatus
from app.services.retry_history_store import RetryHistoryStore, to_retry_history


def make_upload_execution(status=UploadStatus.SUCCESS, upload_id="mock_upload_video.mp4", error=None):
    return UploadExecution(
        video_id="20260716_120000",
        platform="youtube",
        status=status,
        upload_id=upload_id,
        url=None,
        error=error,
    )


class TestRetryHistoryCreation(unittest.TestCase):

    def test_retry_history_can_be_created_with_expected_fields(self):
        history = RetryHistory(
            video_id="20260716_120000",
            platform="youtube",
            attempt=1,
            executed=True,
            upload_id="mock_upload_video.mp4",
            error=None,
            reason="재시도 실행",
        )

        self.assertEqual(history.video_id, "20260716_120000")
        self.assertEqual(history.platform, "youtube")
        self.assertEqual(history.attempt, 1)
        self.assertTrue(history.executed)
        self.assertEqual(history.upload_id, "mock_upload_video.mp4")
        self.assertIsNone(history.error)
        self.assertEqual(history.reason, "재시도 실행")


class TestRetryExecutionToHistoryConversion(unittest.TestCase):

    def test_executed_retry_execution_converts_with_upload_id(self):
        upload_execution = make_upload_execution(status=UploadStatus.SUCCESS, upload_id="mock_upload_video.mp4")
        retry_execution = RetryExecution(
            attempt=2, executed=True, execution=upload_execution, reason="업로드 실패: Mock upload failed",
        )

        history = to_retry_history("20260716_120000", "youtube", retry_execution)

        self.assertIsInstance(history, RetryHistory)
        self.assertEqual(history.video_id, "20260716_120000")
        self.assertEqual(history.platform, "youtube")
        self.assertEqual(history.attempt, 2)
        self.assertTrue(history.executed)
        self.assertEqual(history.upload_id, "mock_upload_video.mp4")
        self.assertIsNone(history.error)
        self.assertEqual(history.reason, "업로드 실패: Mock upload failed")

    def test_executed_retry_execution_converts_with_error(self):
        upload_execution = make_upload_execution(status=UploadStatus.FAILED, upload_id=None, error="Mock upload failed")
        retry_execution = RetryExecution(
            attempt=1, executed=True, execution=upload_execution, reason="업로드 실패: Mock upload failed",
        )

        history = to_retry_history("20260716_120000", "youtube", retry_execution)

        self.assertIsNone(history.upload_id)
        self.assertEqual(history.error, "Mock upload failed")

    def test_not_executed_retry_execution_converts_without_upload_fields(self):
        retry_execution = RetryExecution(
            attempt=1, executed=False, execution=None, reason="업로드 성공",
        )

        history = to_retry_history("20260716_120000", "youtube", retry_execution)

        self.assertFalse(history.executed)
        self.assertIsNone(history.upload_id)
        self.assertIsNone(history.error)
        self.assertEqual(history.reason, "업로드 성공")


class TestRetryHistoryStoreInMemory(unittest.TestCase):

    def test_record_stores_entry_and_returns_it(self):
        store = RetryHistoryStore()
        retry_execution = RetryExecution(
            attempt=1, executed=True, execution=make_upload_execution(), reason="업로드 실패: Mock upload failed",
        )

        recorded = store.record("20260716_120000", "youtube", retry_execution)

        self.assertIsInstance(recorded, RetryHistory)
        self.assertEqual(store.load_all(), [recorded])

    def test_multiple_records_are_all_stored_in_order(self):
        store = RetryHistoryStore()
        first = RetryExecution(attempt=1, executed=True, execution=make_upload_execution(), reason="첫 시도")
        second = RetryExecution(attempt=2, executed=True, execution=make_upload_execution(), reason="두번째 시도")

        store.record("20260716_120000", "youtube", first)
        store.record("20260716_120000", "youtube", second)

        all_records = store.load_all()
        self.assertEqual(len(all_records), 2)
        self.assertEqual(all_records[0].attempt, 1)
        self.assertEqual(all_records[1].attempt, 2)


class TestRetryHistoryStoreQuery(unittest.TestCase):

    def test_load_all_filters_by_video_id(self):
        store = RetryHistoryStore()
        execution = RetryExecution(attempt=1, executed=True, execution=make_upload_execution(), reason="시도")

        store.record("video_a", "youtube", execution)
        store.record("video_b", "youtube", execution)

        filtered = store.load_all(video_id="video_a")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].video_id, "video_a")

    def test_load_all_returns_empty_list_when_no_records_match(self):
        store = RetryHistoryStore()

        self.assertEqual(store.load_all(video_id="nonexistent"), [])


if __name__ == "__main__":
    unittest.main()
