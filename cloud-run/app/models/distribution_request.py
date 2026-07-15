from typing import Optional

from pydantic import BaseModel


class EnqueueRequest(BaseModel):

    video_id: str
    output_path: str
    title: str
    description: str
    hashtags: list[str]
    thumbnail_path: str
    target_platforms: list[str]
    publish_mode: str = "immediate"
    scheduled_at: Optional[str] = None


class ApproveRequest(BaseModel):
    """
    approve 호출 시 함께 넘길 수 있는 필드 수정안(전부 선택).
    None으로 남긴 필드는 수정하지 않는다.
    """

    title: Optional[str] = None
    description: Optional[str] = None
    hashtags: Optional[list[str]] = None
    target_platforms: Optional[list[str]] = None
    publish_mode: Optional[str] = None
    scheduled_at: Optional[str] = None
