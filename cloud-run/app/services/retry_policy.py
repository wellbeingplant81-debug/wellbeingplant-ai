"""
Sprint112 - Distribution Upload Retry Intelligence.

build_retry_plan()은 Sprint111 ReliabilityDecision을 입력으로 받아
재시도 계획(RetryPlan)만 반환하는 순수 함수다. 실제 재시도 실행,
Scheduler, Queue 연결은 이 스프린트 범위 밖이다.

이 파일이 하지 않는 것:
- 실제 재시도 실행
- Scheduler/Queue 연결
"""

from app.models.retry_plan import RetryPlan
from app.models.upload_reliability import ReliabilityDecision, ReliabilityStatus

DEFAULT_MAX_ATTEMPTS = 3


def build_retry_plan(decision: ReliabilityDecision) -> RetryPlan:

    if decision.status == ReliabilityStatus.SUCCESS:
        return RetryPlan(retry=False, max_attempts=0, reason=decision.reason)

    return RetryPlan(
        retry=True, max_attempts=DEFAULT_MAX_ATTEMPTS, reason=decision.reason,
    )
