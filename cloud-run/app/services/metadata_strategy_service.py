"""
Epic 47 Sprint 006 - AI Metadata Engine, Metadata Strategy.

Epic 18의 THUMBNAIL_MODE_BY_RENDER_PROFILE(render_profile별 정책 dict)
과 동일한 패턴이다. Category/Language/Privacy 기본값은 새로 발명하지
않고 기존 값을 재사용/정합화한다(config.DEFAULT_CATEGORY, config.
YOUTUBE_CATEGORY_ID_HOWTO_AND_STYLE, config.YOUTUBE_DEFAULT_LANGUAGE -
전부 이 Sprint에서 config.py에 추가). Publish Strategy만 새 정책 축이다
- Shorts는 "immediate"(현재처럼 publish_at 없이 즉시), Longform은
"scheduled"(Epic46 Sprint005의 publish_at 예약 발행 메커니즘과 짝을
이룬다).

build_default_metadata()는 실제 생성(Gemini 등)이 완전히 실패했을 때를
대비한 안전한 최소 Metadata(app.models.metadata.Metadata, 무수정 모델
재사용)를 만든다 - 새 모델을 만들지 않는다.
"""

from typing import Dict, Optional

from app import config
from app.models.metadata import Metadata
from app.models.metadata_strategy import MetadataStrategy

_SHORTS_STRATEGY = MetadataStrategy(
    category_name=config.DEFAULT_CATEGORY,
    category_id=config.YOUTUBE_CATEGORY_ID_HOWTO_AND_STYLE,
    language=config.YOUTUBE_DEFAULT_LANGUAGE,
    privacy_status="private",
    publish_strategy="immediate",
)

_LONGFORM_STRATEGY = MetadataStrategy(
    category_name=config.DEFAULT_CATEGORY,
    category_id=config.YOUTUBE_CATEGORY_ID_HOWTO_AND_STYLE,
    language=config.YOUTUBE_DEFAULT_LANGUAGE,
    privacy_status="private",
    publish_strategy="scheduled",
)

RENDER_PROFILE_METADATA_STRATEGY: Dict[Optional[str], MetadataStrategy] = {
    "shorts": _SHORTS_STRATEGY,
    "longform": _LONGFORM_STRATEGY,
}


def get_metadata_strategy(render_profile: Optional[str] = None) -> MetadataStrategy:
    return RENDER_PROFILE_METADATA_STRATEGY.get(render_profile, _SHORTS_STRATEGY)


def build_default_metadata(render_profile: Optional[str] = None) -> Metadata:
    strategy = get_metadata_strategy(render_profile)
    return Metadata(
        category=strategy.category_name,
        warnings=config.MEDICAL_DISCLAIMER_TEXT,
    )
