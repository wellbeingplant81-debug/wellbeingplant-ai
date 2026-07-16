"""
Sprint111 - Distribution Upload Reliability Intelligence.

evaluate_reliability()는 Sprint110 UploadExecution.status를 입력으로
받아 재시도 여부를 판단하는 순수 함수다. Sprint107 distribution_decision.py
(analytics 기반 platform 헬스 판단)와는 독립적인 계층이며, Queue/History에는
전혀 연결하지 않는다.

이 파일이 하지 않는 것:
- 실제 재시도 실행(재시도 트리거는 이후 스프린트 범위)
- Queue/History 기록
"""

from app.models.upload_execution import UploadExecution, UploadStatus
from app.models.upload_reliability import ReliabilityDecision, ReliabilityStatus


def evaluate_reliability(execution: UploadExecution) -> ReliabilityDecision:

    if execution.status == UploadStatus.SUCCESS:
        return ReliabilityDecision(
            status=ReliabilityStatus.SUCCESS,
            retryable=False,
            reason="업로드 성공",
        )

    reason = f"업로드 실패: {execution.error}" if execution.error else "업로드 실패"

    return ReliabilityDecision(
        status=ReliabilityStatus.RETRYABLE_FAILURE,
        retryable=True,
        reason=reason,
    )
