"""
Sprint117 - Upload Service Provider Registry Integration.

UploadService의 provider 선택을 Sprint116 UploadProviderRegistry로
공식 통합하는 계약 테스트. 단순히 "동작하는지"만 보지 않는다 -
UploadService는 생성자에 dict를 받든 UploadProviderRegistry를 받든
내부적으로 항상 UploadProviderRegistry 하나의 타입으로 정규화해서
저장해야 한다(현재 구현은 dict를 duck typing으로만 우연히 지원하고
있어 이 정규화 계약을 만족하지 못한다 - 이게 이번 스프린트의 진짜
RED 지점이다).

Provider 구현체(MockUploadProvider/YouTubeUploadProvider)/
UploadExecutor/Retry 계층/distribution 기존 파일은 이 스프린트에서
수정하지 않는다.
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
from app.services.upload_service import UploadService


SAMPLE_METADATA = {
    "title": "제목",
    "description": "설명",
    "hashtags": ["health"],
}


def make_job(platform="youtube"):
    return UploadJob(
        video_id="20260716_120000",
        file_path="output/20260716_120000/final/video.mp4",
        platform=platform,
        metadata=SAMPLE_METADATA,
    )


class TestUploadServiceAcceptsProviderRegistryInjection(unittest.TestCase):

    def test_constructed_with_registry_instance_normalizes_to_registry_type(self):
        registry = UploadProviderRegistry()
        registry.register("youtube", YouTubeUploadProvider())

        service = UploadService(provider_registry=registry)

        self.assertIsInstance(service.provider_registry, UploadProviderRegistry)

    def test_constructed_with_dict_normalizes_to_registry_type(self):
        # 핵심 RED 지점: 지금 구현은 dict를 그대로 self.provider_registry에
        # 저장하므로 이 assertion이 실패한다(duck typing으로만 동작할 뿐,
        # 내부 타입은 dict). Registry가 공식 provider 선택 계층이 되려면
        # dict로 생성해도 내부적으로 UploadProviderRegistry로 변환돼야 한다.
        service = UploadService(provider_registry={"youtube": YouTubeUploadProvider()})

        self.assertIsInstance(service.provider_registry, UploadProviderRegistry)


class TestUploadServiceYouTubePlatformRouting(unittest.TestCase):

    def test_upload_routes_to_youtube_provider_via_registry(self):
        registry = UploadProviderRegistry()
        youtube_provider = YouTubeUploadProvider()
        registry.register("youtube", youtube_provider)
        service = UploadService(provider_registry=registry)
        job = make_job(platform="youtube")

        service.upload(job)

        self.assertEqual(youtube_provider.last_file_path, job.file_path)
        self.assertEqual(youtube_provider.last_metadata, job.metadata)


class TestUploadServiceMockPlatformRouting(unittest.TestCase):

    def test_upload_routes_to_mock_provider_via_registry(self):
        registry = UploadProviderRegistry()
        mock_provider = MockUploadProvider()
        registry.register("mock", mock_provider)
        service = UploadService(provider_registry=registry)
        job = make_job(platform="mock")

        service.upload(job)

        self.assertEqual(mock_provider.last_file_path, job.file_path)
        self.assertEqual(mock_provider.last_metadata, job.metadata)


class TestUploadServiceCallsProviderThroughRegistry(unittest.TestCase):

    def test_upload_actually_invokes_registered_provider(self):
        registry = UploadProviderRegistry()
        provider = MockUploadProvider()
        registry.register("youtube", provider)
        service = UploadService(provider_registry=registry)
        job = make_job(platform="youtube")

        self.assertIsNone(provider.last_file_path)

        service.upload(job)

        self.assertIsNotNone(provider.last_file_path)


class TestUploadServiceReturnsUploadResult(unittest.TestCase):

    def test_upload_returns_upload_result_instance(self):
        registry = UploadProviderRegistry()
        registry.register("youtube", YouTubeUploadProvider())
        service = UploadService(provider_registry=registry)
        job = make_job(platform="youtube")

        result = service.upload(job)

        self.assertIsInstance(result, UploadResult)
        self.assertTrue(result.success)


class TestUploadServiceUnregisteredPlatform(unittest.TestCase):

    def test_upload_raises_for_unregistered_platform_via_registry(self):
        registry = UploadProviderRegistry()
        registry.register("youtube", YouTubeUploadProvider())
        service = UploadService(provider_registry=registry)
        job = make_job(platform="facebook")

        with self.assertRaises(ValueError):
            service.upload(job)


class TestUploadServiceBackwardCompatibleDictConstruction(unittest.TestCase):

    def test_dict_construction_still_routes_correctly(self):
        provider = YouTubeUploadProvider()
        service = UploadService(provider_registry={"youtube": provider})
        job = make_job(platform="youtube")

        result = service.upload(job)

        self.assertTrue(result.success)
        self.assertEqual(provider.last_file_path, job.file_path)

    def test_dict_construction_still_raises_for_unregistered_platform(self):
        service = UploadService(provider_registry={"youtube": YouTubeUploadProvider()})
        job = make_job(platform="facebook")

        with self.assertRaises(ValueError):
            service.upload(job)


if __name__ == "__main__":
    unittest.main()
