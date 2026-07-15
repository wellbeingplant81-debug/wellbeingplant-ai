"""
Sprint104 - Video Distribution Intelligence.

플랫폼별 발행 어댑터의 공통 인터페이스와, 이번 스프린트에 실제로
구현하는 3개 Mock Adapter(YouTube/Instagram/TikTok). 실제 플랫폼 API는
전혀 호출하지 않는다 - 각 Adapter는 자기 자신의
ENABLE_{PLATFORM}_REAL_API 플래그(기본 False)를 확인해서, 켜져 있으면
"진짜 연동된 것처럼" mock 결과를 조용히 반환하는 대신 명시적으로
NotImplementedError를 던진다(실제 API 연결은 별도 Sprint).

이 파일이 하지 않는 것:
- 발행 순서/재시도/상태 전이 판단(distribution_service.py 소관)
- 큐 저장(distribution_store.py 소관)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app import config


@dataclass
class PublishResult:
    success: bool
    platform_post_id: str
    error: str


class PlatformAdapter(ABC):

    @abstractmethod
    def publish(self, queue_item: dict) -> PublishResult:
        raise NotImplementedError


def _mock_or_raise(platform: str, real_api_enabled: bool, queue_item: dict) -> PublishResult:

    if real_api_enabled:
        raise NotImplementedError(
            f"Real {platform} API integration is out of scope for Sprint104 "
            f"(ENABLE_{platform.upper()}_REAL_API is on, but no real "
            f"implementation exists yet)."
        )

    return PublishResult(
        success=True,
        platform_post_id=f"mock_{platform}_{queue_item['video_id']}",
        error=None,
    )


class YouTubeAdapter(PlatformAdapter):

    def publish(self, queue_item: dict) -> PublishResult:
        return _mock_or_raise("youtube", config.ENABLE_YOUTUBE_REAL_API, queue_item)


class InstagramAdapter(PlatformAdapter):

    def publish(self, queue_item: dict) -> PublishResult:
        return _mock_or_raise("instagram", config.ENABLE_INSTAGRAM_REAL_API, queue_item)


class TikTokAdapter(PlatformAdapter):

    def publish(self, queue_item: dict) -> PublishResult:
        return _mock_or_raise("tiktok", config.ENABLE_TIKTOK_REAL_API, queue_item)


_ADAPTER_CLASSES = {
    "youtube": YouTubeAdapter,
    "instagram": InstagramAdapter,
    "tiktok": TikTokAdapter,
}


def get_adapter(platform: str) -> PlatformAdapter:

    adapter_cls = _ADAPTER_CLASSES.get(platform)

    if adapter_cls is None:
        raise ValueError(f"Unknown platform: {platform}")

    return adapter_cls()
