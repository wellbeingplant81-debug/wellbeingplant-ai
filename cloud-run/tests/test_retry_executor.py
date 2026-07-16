"""
Sprint113 - Distribution Retry Execution Intelligence. RetryExecution +
RetryExecutor 계약 테스트.

RetryExecutor는 Sprint112 RetryPlan을 입력으로 받아, plan.retry가
True일 때만 Sprint110 UploadExecutor를 호출해 실제 재시도 1회를
실행하는 계층이다. plan.retry가 False면 UploadExecutor를 아예 호출하지
않는다. Scheduler/Queue 연결, max_attempts 루프 제어는 이번 스프린트
범위 밖이다(단일 시도 실행만 담당). upload_executor.py/upload_service.py/
upload_provider.py/upload_reliability.py/retry_policy.py는 이 스프린트에서
수정하지 않는다.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.retry_execution import RetryExecution
from app.models.retry_plan import RetryPlan
from app.models.upload_execution import UploadExecution, UploadStatus
from app.models.upload_job import UploadJob
from app.services.retry_executor import RetryExecutor
from app.services.upload_executor import UploadExecutor


SAMPLE_METADATA = {
    "title": "제목",
    "description": "설명",
    "hashtags": ["health"],
}


def make_job():
    return UploadJob(
        video_id="20260716_120000",
        file_path="output/20260716_120000/final/video.mp4",
        platform="youtube",
        metadata=SAMPLE_METADATA,
    )


def make_execution(status=UploadStatus.SUCCESS, upload_id="mock_upload_video.mp4", error=None):
    return UploadExecution(
        video_id="20260716_120000",
        platform="youtube",
        status=status,
        upload_id=upload_id,
        url=None,
        error=error,
    )


class TestRetryExecutionCreation(unittest.TestCase):

    def test_retry_execution_can_be_created_with_expected_fields(self):
        execution = make_execution()
        retry_execution = RetryExecution(
            attempt=1, executed=True, execution=execution, reason="재시도 실행",
        )

        self.assertEqual(retry_execution.attempt, 1)
        self.assertTrue(retry_execution.executed)
        self.assertEqual(retry_execution.execution, execution)
        self.assertEqual(retry_execution.reason, "재시도 실행")


class TestRetryExecutorSkipsWhenPlanRetryFalse(unittest.TestCase):

    def test_execute_does_not_call_upload_executor(self):
        upload_executor = MagicMock(spec=UploadExecutor)
        retry_executor = RetryExecutor(upload_executor)
        plan = RetryPlan(retry=False, max_attempts=0, reason="업로드 성공")
        job = make_job()

        retry_executor.execute(plan, job, attempt=1)

        upload_executor.execute.assert_not_called()

    def test_execute_returns_not_executed_retry_execution(self):
        upload_executor = MagicMock(spec=UploadExecutor)
        retry_executor = RetryExecutor(upload_executor)
        plan = RetryPlan(retry=False, max_attempts=0, reason="업로드 성공")
        job = make_job()

        result = retry_executor.execute(plan, job, attempt=1)

        self.assertIsInstance(result, RetryExecution)
        self.assertFalse(result.executed)
        self.assertIsNone(result.execution)


class TestRetryExecutorCallsUploadExecutorWhenPlanRetryTrue(unittest.TestCase):

    def test_execute_calls_upload_executor_with_job(self):
        upload_executor = MagicMock(spec=UploadExecutor)
        upload_executor.execute.return_value = make_execution()
        retry_executor = RetryExecutor(upload_executor)
        plan = RetryPlan(retry=True, max_attempts=3, reason="업로드 실패: Mock upload failed")
        job = make_job()

        retry_executor.execute(plan, job, attempt=1)

        upload_executor.execute.assert_called_once_with(job)


class TestRetryExecutorAttempt(unittest.TestCase):

    def test_attempt_value_carries_through(self):
        upload_executor = MagicMock(spec=UploadExecutor)
        upload_executor.execute.return_value = make_execution()
        retry_executor = RetryExecutor(upload_executor)
        plan = RetryPlan(retry=True, max_attempts=3, reason="업로드 실패: Mock upload failed")
        job = make_job()

        result = retry_executor.execute(plan, job, attempt=2)

        self.assertEqual(result.attempt, 2)


class TestRetryExecutorReturnsUploadExecution(unittest.TestCase):

    def test_execute_returns_upload_executor_result_as_execution(self):
        upload_executor = MagicMock(spec=UploadExecutor)
        expected_execution = make_execution(status=UploadStatus.SUCCESS)
        upload_executor.execute.return_value = expected_execution
        retry_executor = RetryExecutor(upload_executor)
        plan = RetryPlan(retry=True, max_attempts=3, reason="업로드 실패: Mock upload failed")
        job = make_job()

        result = retry_executor.execute(plan, job, attempt=1)

        self.assertIsInstance(result, RetryExecution)
        self.assertTrue(result.executed)
        self.assertEqual(result.execution, expected_execution)


class TestRetryExecutorReason(unittest.TestCase):

    def test_reason_reflects_plan_reason_when_not_executed(self):
        upload_executor = MagicMock(spec=UploadExecutor)
        retry_executor = RetryExecutor(upload_executor)
        plan = RetryPlan(retry=False, max_attempts=0, reason="업로드 성공")
        job = make_job()

        result = retry_executor.execute(plan, job, attempt=1)

        self.assertEqual(result.reason, "업로드 성공")

    def test_reason_reflects_plan_reason_when_executed(self):
        upload_executor = MagicMock(spec=UploadExecutor)
        upload_executor.execute.return_value = make_execution()
        retry_executor = RetryExecutor(upload_executor)
        plan = RetryPlan(retry=True, max_attempts=3, reason="업로드 실패: Mock upload failed")
        job = make_job()

        result = retry_executor.execute(plan, job, attempt=1)

        self.assertEqual(result.reason, "업로드 실패: Mock upload failed")


if __name__ == "__main__":
    unittest.main()
