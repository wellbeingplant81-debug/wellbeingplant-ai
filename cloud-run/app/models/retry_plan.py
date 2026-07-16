"""
Sprint112 - Distribution Upload Retry Intelligence. 순수 데이터
모델이다 - 판단 로직은 여기 넣지 않는다(그건 retry_policy.py의 책임).
"""

from pydantic import BaseModel


class RetryPlan(BaseModel):
    retry: bool
    max_attempts: int
    reason: str
