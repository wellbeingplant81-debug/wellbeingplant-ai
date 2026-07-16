"""
Sprint116 - Upload Provider Registry Intelligence.

UploadProviderRegistry는 platform 이름으로 UploadProvider 인스턴스를
등록/조회하는 순수 선택 계층이다. UploadService/UploadExecutor에는
연결하지 않는다(이번 스프린트 범위 밖). 실제 API/OAuth 연결 없음.
"""

from app.providers.upload.upload_provider import UploadProvider


class UploadProviderRegistry:

    def __init__(self):
        self._providers: dict[str, UploadProvider] = {}

    def register(self, platform: str, provider: UploadProvider) -> None:
        self._providers[platform] = provider

    def get(self, platform: str) -> UploadProvider:
        provider = self._providers.get(platform)

        if provider is None:
            raise ValueError(f"No upload provider registered for platform: {platform}")

        return provider
