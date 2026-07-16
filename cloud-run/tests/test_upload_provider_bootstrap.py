"""
Sprint119 - Upload Provider Bootstrap Intelligence. UploadProviderBootstrap
계약 테스트.

UploadProviderBootstrap은 Sprint118 UploadProviderFactory + Sprint116
UploadProviderRegistry + Sprint109/117 UploadService를 조립하는 계층이다.
새 선택/생성 로직을 추가하지 않고 기존 3개 계층을 연결만 한다. 실제
YouTube API/OAuth는 다루지 않으며, Retry/Distribution에는 연결하지
않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.upload_job import UploadJob
from app.providers.upload.mock_upload_provider import MockUploadProvider
from app.providers.upload.provider_registry import UploadProviderRegistry
from app.providers.upload.upload_provider import UploadResult
from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider
from app.services.upload_provider_bootstrap import UploadProviderBootstrap
from app.services.upload_service import UploadService


class TestUploadProviderBootstrapCreation(unittest.TestCase):

    def test_bootstrap_can_be_created(self):
        bootstrap = UploadProviderBootstrap()
        self.assertIsInstance(bootstrap, UploadProviderBootstrap)


class TestUploadProviderBootstrapCreateRegistry(unittest.TestCase):

    def test_create_registry_returns_upload_provider_registry(self):
        bootstrap = UploadProviderBootstrap()

        registry = bootstrap.create_registry()

        self.assertIsInstance(registry, UploadProviderRegistry)


class TestUploadProviderBootstrapRegistryYouTube(unittest.TestCase):

    def test_registry_contains_youtube_provider(self):
        bootstrap = UploadProviderBootstrap()
        registry = bootstrap.create_registry()

        provider = registry.get("youtube")

        self.assertIsInstance(provider, YouTubeUploadProvider)


class TestUploadProviderBootstrapRegistryMock(unittest.TestCase):

    def test_registry_contains_mock_provider(self):
        bootstrap = UploadProviderBootstrap()
        registry = bootstrap.create_registry()

        provider = registry.get("mock")

        self.assertIsInstance(provider, MockUploadProvider)


class TestUploadProviderBootstrapCreateUploadService(unittest.TestCase):

    def test_create_upload_service_returns_upload_service(self):
        bootstrap = UploadProviderBootstrap()

        service = bootstrap.create_upload_service()

        self.assertIsInstance(service, UploadService)


class TestUploadProviderBootstrapServiceInternalRegistry(unittest.TestCase):

    def test_created_service_provider_registry_is_upload_provider_registry(self):
        bootstrap = UploadProviderBootstrap()

        service = bootstrap.create_upload_service()

        self.assertIsInstance(service.provider_registry, UploadProviderRegistry)


class TestUploadProviderBootstrapEndToEndUpload(unittest.TestCase):

    def test_bootstrapped_service_upload_flow_works(self):
        bootstrap = UploadProviderBootstrap()
        service = bootstrap.create_upload_service()
        job = UploadJob(
            video_id="20260716_120000",
            file_path="output/20260716_120000/final/video.mp4",
            platform="youtube",
            metadata={"title": "제목", "description": "설명", "hashtags": ["health"]},
        )

        result = service.upload(job)

        self.assertIsInstance(result, UploadResult)
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
