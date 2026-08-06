"""
Sprint118 - Upload Provider Factory Intelligence. UploadProviderFactory
계약 테스트.

UploadProviderFactory는 platform 이름으로 UploadProvider 구현체
(Sprint108 MockUploadProvider/Sprint115 YouTubeUploadProvider)를 생성하고,
Sprint116 UploadProviderRegistry에 등록해 반환하는 계층이다. 실제
YouTube API/OAuth는 전혀 다루지 않는다.

app/services/provider_factory.py(Asset Pipeline용 Pexels/Pixabay
source chain, 무관한 도메인)와 이름이 겹치지만 완전히 별개 모듈이다 -
그 파일과 tests/test_provider_factory.py는 이 스프린트에서 건드리지
않는다. upload_service.py/upload_executor.py/Provider 구현체/
Distribution 기존 파일도 수정하지 않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.mock_upload_provider import MockUploadProvider
from app.providers.upload.provider_factory import UploadProviderFactory
from app.providers.upload.provider_registry import UploadProviderRegistry
from app.providers.upload.upload_provider import UploadProvider
from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider


class TestUploadProviderFactoryCreation(unittest.TestCase):

    def test_factory_can_be_created(self):
        factory = UploadProviderFactory()
        self.assertIsInstance(factory, UploadProviderFactory)


class TestUploadProviderFactoryCreatesYouTube(unittest.TestCase):

    def test_create_youtube_returns_youtube_upload_provider(self):
        factory = UploadProviderFactory()

        provider = factory.create("youtube")

        self.assertIsInstance(provider, YouTubeUploadProvider)


class TestUploadProviderFactoryCreatesMock(unittest.TestCase):

    def test_create_mock_returns_mock_upload_provider(self):
        factory = UploadProviderFactory()

        provider = factory.create("mock")

        self.assertIsInstance(provider, MockUploadProvider)


class TestUploadProviderFactoryContractCompliance(unittest.TestCase):

    def test_created_youtube_provider_is_upload_provider(self):
        factory = UploadProviderFactory()

        provider = factory.create("youtube")

        self.assertIsInstance(provider, UploadProvider)

    def test_created_mock_provider_is_upload_provider(self):
        factory = UploadProviderFactory()

        provider = factory.create("mock")

        self.assertIsInstance(provider, UploadProvider)


class TestUploadProviderFactoryUnsupportedPlatform(unittest.TestCase):

    def test_create_raises_for_unsupported_platform(self):
        factory = UploadProviderFactory()

        with self.assertRaises(ValueError):
            factory.create("facebook")


class TestUploadProviderFactoryBuildRegistry(unittest.TestCase):

    def test_build_registry_returns_upload_provider_registry(self):
        factory = UploadProviderFactory()

        registry = factory.build_registry()

        self.assertIsInstance(registry, UploadProviderRegistry)


class TestUploadProviderFactoryRegistryLookup(unittest.TestCase):

    def test_build_registry_allows_youtube_lookup(self):
        factory = UploadProviderFactory()
        registry = factory.build_registry()

        provider = registry.get("youtube")

        self.assertIsInstance(provider, YouTubeUploadProvider)

    def test_build_registry_allows_mock_lookup(self):
        factory = UploadProviderFactory()
        registry = factory.build_registry()

        provider = registry.get("mock")

        self.assertIsInstance(provider, MockUploadProvider)


if __name__ == "__main__":
    unittest.main()
