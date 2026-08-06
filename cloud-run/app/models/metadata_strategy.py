"""
Epic 47 Sprint 006 - AI Metadata Engine, Metadata Strategy.

render_profile(Shorts/Longform)별 Category/Language/Privacy/Publish
Strategy 기본값을 담는 값 객체다.
"""

from dataclasses import dataclass


@dataclass
class MetadataStrategy:
    category_name: str
    category_id: str
    language: str
    privacy_status: str
    publish_strategy: str
