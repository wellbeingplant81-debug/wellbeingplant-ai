"""
Sprint114 - Distribution Retry History Intelligence.

Sprint113 RetryExecution 결과를 RetryHistory로 변환해 InMemory로만
저장/조회한다. 파일 I/O/DB/Queue/Scheduler는 전혀 사용하지 않는다.
Sprint105 distribution_history.py(파일 기반 발행 이력)와는 독립적인
계층이다.

이 파일이 하지 않는 것:
- 파일/DB 영속화
- Queue/Scheduler 연결
"""

from typing import Optional

from app.models.retry_execution import RetryExecution
from app.models.retry_history import RetryHistory


def to_retry_history(video_id: str, platform: str, retry_execution: RetryExecution) -> RetryHistory:

    upload_id = None
    error = None

    if retry_execution.executed and retry_execution.execution is not None:
        upload_id = retry_execution.execution.upload_id
        error = retry_execution.execution.error

    return RetryHistory(
        video_id=video_id,
        platform=platform,
        attempt=retry_execution.attempt,
        executed=retry_execution.executed,
        upload_id=upload_id,
        error=error,
        reason=retry_execution.reason,
    )


class RetryHistoryStore:

    def __init__(self):
        self._records: list[RetryHistory] = []

    def record(self, video_id: str, platform: str, retry_execution: RetryExecution) -> RetryHistory:
        entry = to_retry_history(video_id, platform, retry_execution)
        self._records.append(entry)
        return entry

    def load_all(self, video_id: Optional[str] = None) -> list[RetryHistory]:
        if video_id is not None:
            return [r for r in self._records if r.video_id == video_id]

        return list(self._records)
