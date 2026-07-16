"""
Sprint109 - Distribution Upload Workflow Foundation. 순수 데이터 모델이다 -
provider 선택/호출 로직은 여기 넣지 않는다(그건 upload_service.py의 책임).
"""

from pydantic import BaseModel


class UploadJob(BaseModel):
    video_id: str
    file_path: str
    platform: str
    metadata: dict
