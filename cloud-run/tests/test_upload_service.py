"""
Sprint109 - Distribution Upload Workflow Foundation. UploadJob + UploadService
계약 테스트.

UploadService는 Sprint108의 UploadProvider 인터페이스(app.providers.upload)
위에서 "어떤 platform이면 어떤 provider를 호출할지" 라우팅만 담당한다.
Sprint104 platform_adapter.py(distribution 큐 아이템 → 발행 판단)와는
독립적인 계층이며, distribution_queue.py/distribution_history.py에는
전혀 연결하지 않는다 - provider_registry는 생성자로 주입받아 테스트에서
Mock provider를 자유롭게 교체할 수 있게 한다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.mock_upload_provider import MockUploadProvider
from app.providers.upload.upload_provider import UploadResult
from app.services.upload_service import UploadJob, UploadService


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


class TestUploadJobCreation(unittest.TestCase):

    def test_upload_job_can_be_created_with_expected_fields(self):
        job = make_job()

        self.assertEqual(job.video_id, "20260716_120000")
        self.assertEqual(job.file_path, "output/20260716_120000/final/video.mp4")
        self.assertEqual(job.platform, "youtube")
        self.assertEqual(job.metadata, SAMPLE_METADATA)


class TestUploadServiceCallsProvider(unittest.TestCase):

    def test_upload_calls_registered_provider_with_file_path_and_metadata(self):
        provider = MockUploadProvider()
        service = UploadService(provider_registry={"youtube": provider})
        job = make_job(platform="youtube")

        service.upload(job)

        self.assertEqual(provider.last_file_path, job.file_path)
        self.assertEqual(provider.last_metadata, job.metadata)
        self.assertIs(provider.last_metadata, job.metadata)


class TestUploadServicePlatformSelection(unittest.TestCase):

    def test_upload_routes_to_provider_registered_for_job_platform(self):
        youtube_provider = MockUploadProvider()
        instagram_provider = MockUploadProvider()
        service = UploadService(provider_registry={
            "youtube": youtube_provider,
            "instagram": instagram_provider,
        })
        job = make_job(platform="instagram")

        service.upload(job)

        self.assertIsNotNone(instagram_provider.last_file_path)
        self.assertIsNone(youtube_provider.last_file_path)

    def test_upload_raises_for_unregistered_platform(self):
        service = UploadService(provider_registry={"youtube": MockUploadProvider()})
        job = make_job(platform="facebook")

        with self.assertRaises(ValueError):
            service.upload(job)


class TestUploadServiceResult(unittest.TestCase):

    def test_upload_returns_success_upload_result_from_provider(self):
        provider = MockUploadProvider()
        service = UploadService(provider_registry={"youtube": provider})
        job = make_job(platform="youtube")

        result = service.upload(job)

        self.assertIsInstance(result, UploadResult)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.upload_id)
        self.assertIsNone(result.error)

    def test_upload_returns_failure_upload_result_without_raising(self):
        provider = MockUploadProvider(should_fail=True)
        service = UploadService(provider_registry={"youtube": provider})
        job = make_job(platform="youtube")

        try:
            result = service.upload(job)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"UploadService.upload() raised unexpectedly on provider failure: {exc}")

        self.assertIsInstance(result, UploadResult)
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main()
