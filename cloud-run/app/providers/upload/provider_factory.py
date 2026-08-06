"""
Sprint118 - Upload Provider Factory Intelligence.

UploadProviderFactory는 platform 이름으로 UploadProvider 구현체를
생성하고, Sprint116 UploadProviderRegistry에 등록해 반환한다. 실제
YouTube API/OAuth는 전혀 다루지 않는다.

app/services/provider_factory.py(Asset Pipeline용 Pexels/Pixabay
source chain)와 이름이 겹치지만 완전히 별개 모듈이다 - 그 파일은
건드리지 않는다.
"""

from app.providers.upload.mock_upload_provider import MockUploadProvider
from app.providers.upload.provider_registry import UploadProviderRegistry
from app.providers.upload.upload_provider import UploadProvider
from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider

_SUPPORTED_PLATFORMS = ("youtube", "mock")


class UploadProviderFactory:

    def create(self, platform: str) -> UploadProvider:
        if platform == "youtube":
            return YouTubeUploadProvider()

        if platform == "mock":
            return MockUploadProvider()

        raise ValueError(f"Unsupported upload platform: {platform}")

    def build_registry(self) -> UploadProviderRegistry:
        registry = UploadProviderRegistry()

        for platform in _SUPPORTED_PLATFORMS:
            registry.register(platform, self.create(platform))

        return registry
