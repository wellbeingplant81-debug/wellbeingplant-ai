"""
Sprint113 - Distribution Retry Execution Intelligence.

RetryExecutor는 Sprint112 RetryPlan을 입력으로 받아, plan.retry가
True일 때만 Sprint110 UploadExecutor를 호출해 실제 재시도 1회를
실행한다. plan.retry가 False면 UploadExecutor를 호출하지 않는다.

이 파일이 하지 않는 것:
- max_attempts 루프 제어(호출자 소관 - attempt는 인자로 그대로 받는다)
- Scheduler/Queue 연결
"""

from app.models.retry_execution import RetryExecution
from app.models.retry_plan import RetryPlan
from app.models.upload_job import UploadJob


class RetryExecutor:

    def __init__(self, upload_executor):
        self.upload_executor = upload_executor

    def execute(self, plan: RetryPlan, job: UploadJob, attempt: int) -> RetryExecution:

        if not plan.retry:
            return RetryExecution(
                attempt=attempt, executed=False, execution=None, reason=plan.reason,
            )

        execution = self.upload_executor.execute(job)

        return RetryExecution(
            attempt=attempt, executed=True, execution=execution, reason=plan.reason,
        )
