"""
Sprint110 - Distribution Upload Execution Intelligence. 순수 데이터
모델이다 - 변환/실행 로직은 여기 넣지 않는다(그건 upload_executor.py의
책임).
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class UploadStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"


class UploadExecution(BaseModel):
    video_id: str
    platform: str
    status: UploadStatus
    upload_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
