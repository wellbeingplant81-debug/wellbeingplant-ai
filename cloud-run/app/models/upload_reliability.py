"""
Sprint111 - Distribution Upload Reliability Intelligence. 순수 데이터
모델이다 - 판단 로직은 여기 넣지 않는다(그건 upload_reliability.py
서비스 모듈의 책임).
"""

from enum import Enum

from pydantic import BaseModel


class ReliabilityStatus(Enum):
    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"


class ReliabilityDecision(BaseModel):
    status: ReliabilityStatus
    retryable: bool
    reason: str
