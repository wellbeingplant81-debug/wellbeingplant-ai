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

    # Sprint105 §5 - Review Metadata snapshot. Distribution Layer가
    # Pipeline 내부를 직접 조회하지 않는다 - 호출자가 enqueue 시점에
    # 값을 채워 넣는다(전부 선택, 없으면 None). thumbnail_preview는
    # §8-1 결정에 따라 추가하지 않고 기존 thumbnail_path를 재사용한다.
    video_duration: Optional[float] = None
    quality_score: Optional[float] = None
    generation_time: Optional[float] = None
    source_project: Optional[str] = None


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
