"""
Sprint113 - Distribution Retry Execution Intelligence. 순수 데이터
모델이다 - 실행 로직은 여기 넣지 않는다(그건 retry_executor.py의 책임).
"""

from typing import Optional

from pydantic import BaseModel

from app.models.upload_execution import UploadExecution


class RetryExecution(BaseModel):
    attempt: int
    executed: bool
    execution: Optional[UploadExecution] = None
    reason: str
