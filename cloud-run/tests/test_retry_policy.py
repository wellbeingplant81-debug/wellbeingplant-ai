"""
Sprint112 - Distribution Upload Retry Intelligence. RetryPlan +
build_retry_plan() 계약 테스트.

build_retry_plan()은 Sprint111 ReliabilityDecision(status: SUCCESS/
RETRYABLE_FAILURE)을 입력으로 받아 재시도 계획(RetryPlan)만 반환하는
순수 함수다 - 실제 재시도를 실행하거나 Queue/Scheduler를 건드리지
않는다. upload_provider/service/executor/reliability는 이 스프린트에서
수정하지 않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.retry_plan import RetryPlan
from app.models.upload_reliability import ReliabilityDecision, ReliabilityStatus
from app.services.retry_policy import build_retry_plan


def make_decision(status: ReliabilityStatus, retryable: bool, reason: str = "reason"):
    return ReliabilityDecision(status=status, retryable=retryable, reason=reason)


class TestRetryPlanCreation(unittest.TestCase):

    def test_retry_plan_can_be_created_with_expected_fields(self):
        plan = RetryPlan(retry=True, max_attempts=3, reason="재시도 가능한 실패")

        self.assertTrue(plan.retry)
        self.assertEqual(plan.max_attempts, 3)
        self.assertEqual(plan.reason, "재시도 가능한 실패")


class TestBuildRetryPlanSuccess(unittest.TestCase):

    def test_success_decision_returns_retry_false(self):
        decision = make_decision(ReliabilityStatus.SUCCESS, retryable=False, reason="업로드 성공")

        plan = build_retry_plan(decision)

        self.assertIsInstance(plan, RetryPlan)
        self.assertFalse(plan.retry)


class TestBuildRetryPlanFailure(unittest.TestCase):

    def test_retryable_failure_decision_returns_retry_true(self):
        decision = make_decision(
            ReliabilityStatus.RETRYABLE_FAILURE, retryable=True, reason="업로드 실패: Mock upload failed",
        )

        plan = build_retry_plan(decision)

        self.assertIsInstance(plan, RetryPlan)
        self.assertTrue(plan.retry)


class TestBuildRetryPlanMaxAttempts(unittest.TestCase):

    def test_retryable_failure_has_positive_max_attempts(self):
        decision = make_decision(ReliabilityStatus.RETRYABLE_FAILURE, retryable=True)

        plan = build_retry_plan(decision)

        self.assertGreater(plan.max_attempts, 0)

    def test_success_has_zero_max_attempts(self):
        decision = make_decision(ReliabilityStatus.SUCCESS, retryable=False)

        plan = build_retry_plan(decision)

        self.assertEqual(plan.max_attempts, 0)


class TestBuildRetryPlanReason(unittest.TestCase):

    def test_reason_is_non_empty_string(self):
        decision = make_decision(
            ReliabilityStatus.RETRYABLE_FAILURE, retryable=True, reason="업로드 실패: Mock upload failed",
        )

        plan = build_retry_plan(decision)

        self.assertIsInstance(plan.reason, str)
        self.assertTrue(len(plan.reason) > 0)

    def test_reason_reflects_decision_reason(self):
        decision = make_decision(
            ReliabilityStatus.RETRYABLE_FAILURE, retryable=True, reason="업로드 실패: Mock upload failed",
        )

        plan = build_retry_plan(decision)

        self.assertIn("Mock upload failed", plan.reason)


if __name__ == "__main__":
    unittest.main()
