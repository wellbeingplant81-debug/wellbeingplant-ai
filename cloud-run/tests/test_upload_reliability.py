"""
Sprint111 - Distribution Upload Reliability Intelligence. ReliabilityStatus
+ ReliabilityDecision + evaluate_reliability() 계약 테스트.

evaluate_reliability()는 Sprint110 UploadExecution(status: SUCCESS/FAILED)을
입력으로 받아 재시도 판단(ReliabilityDecision)을 반환하는 순수 함수다 -
Sprint107 distribution_decision.py(analytics 기반 platform 헬스 판단)와는
독립적인 계층이며, Queue/History에는 전혀 연결하지 않는다. upload_provider/
upload_service/upload_executor는 이 스프린트에서 수정하지 않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.upload_execution import UploadExecution, UploadStatus
from app.models.upload_reliability import ReliabilityDecision, ReliabilityStatus
from app.services.upload_reliability import evaluate_reliability


def make_execution(status: UploadStatus, error=None, upload_id=None):
    return UploadExecution(
        video_id="20260716_120000",
        platform="youtube",
        status=status,
        upload_id=upload_id,
        url=None,
        error=error,
    )


class TestReliabilityStatusValues(unittest.TestCase):

    def test_reliability_status_has_success_and_retryable_failure_values(self):
        self.assertEqual(ReliabilityStatus.SUCCESS.value, "success")
        self.assertEqual(ReliabilityStatus.RETRYABLE_FAILURE.value, "retryable_failure")


class TestReliabilityDecisionCreation(unittest.TestCase):

    def test_reliability_decision_can_be_created_with_expected_fields(self):
        decision = ReliabilityDecision(
            status=ReliabilityStatus.SUCCESS, retryable=False, reason="업로드 성공",
        )

        self.assertEqual(decision.status, ReliabilityStatus.SUCCESS)
        self.assertFalse(decision.retryable)
        self.assertEqual(decision.reason, "업로드 성공")


class TestEvaluateReliabilitySuccess(unittest.TestCase):

    def test_success_execution_returns_success_decision(self):
        execution = make_execution(UploadStatus.SUCCESS, upload_id="mock_upload_video.mp4")

        decision = evaluate_reliability(execution)

        self.assertIsInstance(decision, ReliabilityDecision)
        self.assertEqual(decision.status, ReliabilityStatus.SUCCESS)

    def test_success_execution_is_not_retryable(self):
        execution = make_execution(UploadStatus.SUCCESS, upload_id="mock_upload_video.mp4")

        decision = evaluate_reliability(execution)

        self.assertFalse(decision.retryable)

    def test_success_execution_reason_is_non_empty(self):
        execution = make_execution(UploadStatus.SUCCESS, upload_id="mock_upload_video.mp4")

        decision = evaluate_reliability(execution)

        self.assertIsInstance(decision.reason, str)
        self.assertTrue(len(decision.reason) > 0)


class TestEvaluateReliabilityFailure(unittest.TestCase):

    def test_failed_execution_returns_retryable_failure_decision(self):
        execution = make_execution(UploadStatus.FAILED, error="Mock upload failed")

        decision = evaluate_reliability(execution)

        self.assertIsInstance(decision, ReliabilityDecision)
        self.assertEqual(decision.status, ReliabilityStatus.RETRYABLE_FAILURE)

    def test_failed_execution_is_retryable(self):
        execution = make_execution(UploadStatus.FAILED, error="Mock upload failed")

        decision = evaluate_reliability(execution)

        self.assertTrue(decision.retryable)

    def test_failed_execution_reason_reflects_execution_error(self):
        execution = make_execution(UploadStatus.FAILED, error="Mock upload failed")

        decision = evaluate_reliability(execution)

        self.assertIn("Mock upload failed", decision.reason)


if __name__ == "__main__":
    unittest.main()
