"""
Epic 17 - Metadata Intelligence.

Metadata: Script(app.services.script_scene_builder.build_script_from_
plan()이 조립하는 dict - title/hook/script/scenes)만을 입력으로 만든
YouTube 업로드 메타데이터. 향후 확장 가능하도록 필드를 전부 Optional/
기본 빈 리스트로 설계한다 - 새 필드가 필요하면 이 모델에 하나만
추가하면 된다.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    hashtags: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    thumbnail_text: Optional[str] = None
    warnings: Optional[str] = None
