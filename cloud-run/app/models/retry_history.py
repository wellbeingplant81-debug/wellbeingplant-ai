"""
Sprint114 - Distribution Retry History Intelligence. 순수 데이터
모델이다 - 변환/저장 로직은 여기 넣지 않는다(그건 retry_history_store.py의
책임).
"""

from typing import Optional

from pydantic import BaseModel


class RetryHistory(BaseModel):
    video_id: str
    platform: str
    attempt: int
    executed: bool
    upload_id: Optional[str] = None
    error: Optional[str] = None
    reason: str
