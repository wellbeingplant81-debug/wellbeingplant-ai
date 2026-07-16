"""
Sprint116 - Upload Provider Registry Intelligence. UploadProviderRegistry
계약 테스트.

UploadProviderRegistry는 platform 이름으로 UploadProvider 인스턴스를
등록/조회하는 순수 선택 계층이다 - Sprint108 UploadProvider 구현체
(MockUploadProvider/YouTubeUploadProvider)는 그대로 재사용하고 수정하지
않는다. UploadService/UploadExecutor에는 아직 연결하지 않는다(이번
스프린트 범위 밖). 실제 API/OAuth 연결 없음.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.mock_upload_provider import MockUploadProvider
from app.providers.upload.provider_registry import UploadProviderRegistry
from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider


class TestProviderRegistryCreation(unittest.TestCase):

    def test_registry_can_be_created(self):
        registry = UploadProviderRegistry()
        self.assertIsInstance(registry, UploadProviderRegistry)


class TestProviderRegistryRegistration(unittest.TestCase):

    def test_register_does_not_raise(self):
        registry = UploadProviderRegistry()
        provider = MockUploadProvider()

        try:
            registry.register("mock", provider)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"register() raised unexpectedly: {exc}")


class TestProviderRegistryYouTubeLookup(unittest.TestCase):

    def test_get_returns_registered_youtube_provider(self):
        registry = UploadProviderRegistry()
        youtube_provider = YouTubeUploadProvider()
        registry.register("youtube", youtube_provider)

        result = registry.get("youtube")

        self.assertIsInstance(result, YouTubeUploadProvider)


class TestProviderRegistryMockLookup(unittest.TestCase):

    def test_get_returns_registered_mock_provider(self):
        registry = UploadProviderRegistry()
        mock_provider = MockUploadProvider()
        registry.register("mock", mock_provider)

        result = registry.get("mock")

        self.assertIsInstance(result, MockUploadProvider)


class TestProviderRegistryUnregisteredPlatform(unittest.TestCase):

    def test_get_raises_for_unregistered_platform(self):
        registry = UploadProviderRegistry()

        with self.assertRaises(ValueError):
            registry.get("facebook")


class TestProviderRegistryIdentity(unittest.TestCase):

    def test_get_returns_exact_same_instance_registered(self):
        registry = UploadProviderRegistry()
        provider = YouTubeUploadProvider()
        registry.register("youtube", provider)

        result = registry.get("youtube")

        self.assertIs(result, provider)


if __name__ == "__main__":
    unittest.main()
