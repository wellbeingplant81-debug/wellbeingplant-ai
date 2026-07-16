"""
Sprint110 - Distribution Upload Execution Intelligence. UploadStatus +
UploadExecution + UploadExecutor 계약 테스트.

UploadExecutor는 Sprint109 UploadService(job.platform 기반 provider
라우팅) 위에서 "실행 결과를 UploadExecution 레코드로 정규화"만 담당한다.
Sprint104 platform_adapter.py(distribution 큐 아이템 → 발행 판단)와는
독립적인 계층이며, distribution_queue.py/distribution_history.py에는
전혀 연결하지 않는다.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.upload_execution import UploadExecution, UploadStatus
from app.models.upload_job import UploadJob
from app.providers.upload.mock_upload_provider import MockUploadProvider
from app.providers.upload.upload_provider import UploadResult
from app.services.upload_executor import UploadExecutor
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


class TestUploadStatusValues(unittest.TestCase):

    def test_upload_status_has_success_and_failed_values(self):
        self.assertEqual(UploadStatus.SUCCESS.value, "success")
        self.assertEqual(UploadStatus.FAILED.value, "failed")


class TestUploadExecutionCreation(unittest.TestCase):

    def test_upload_execution_can_be_created_with_expected_fields(self):
        execution = UploadExecution(
            video_id="20260716_120000",
            platform="youtube",
            status=UploadStatus.SUCCESS,
            upload_id="mock_upload_video.mp4",
            url="https://mock.upload.local/mock_upload_video.mp4",
            error=None,
        )

        self.assertEqual(execution.video_id, "20260716_120000")
        self.assertEqual(execution.platform, "youtube")
        self.assertEqual(execution.status, UploadStatus.SUCCESS)
        self.assertEqual(execution.upload_id, "mock_upload_video.mp4")
        self.assertIsNone(execution.error)


class TestUploadExecutorCallsUploadService(unittest.TestCase):

    def test_execute_calls_upload_service_upload_with_job(self):
        upload_service = MagicMock(spec=UploadService)
        upload_service.upload.return_value = UploadResult(
            success=True, upload_id="abc", url="https://example.com/abc", error=None,
        )
        executor = UploadExecutor(upload_service)
        job = make_job()

        executor.execute(job)

        upload_service.upload.assert_called_once_with(job)


class TestUploadExecutorSuccessExecution(unittest.TestCase):

    def test_execute_returns_success_upload_execution(self):
        provider = MockUploadProvider()
        upload_service = UploadService(provider_registry={"youtube": provider})
        executor = UploadExecutor(upload_service)
        job = make_job(platform="youtube")

        execution = executor.execute(job)

        self.assertIsInstance(execution, UploadExecution)
        self.assertEqual(execution.status, UploadStatus.SUCCESS)
        self.assertEqual(execution.video_id, job.video_id)
        self.assertEqual(execution.platform, job.platform)


class TestUploadExecutorFailedExecution(unittest.TestCase):

    def test_execute_returns_failed_upload_execution(self):
        provider = MockUploadProvider(should_fail=True)
        upload_service = UploadService(provider_registry={"youtube": provider})
        executor = UploadExecutor(upload_service)
        job = make_job(platform="youtube")

        execution = executor.execute(job)

        self.assertIsInstance(execution, UploadExecution)
        self.assertEqual(execution.status, UploadStatus.FAILED)
        self.assertEqual(execution.video_id, job.video_id)
        self.assertEqual(execution.platform, job.platform)


class TestUploadExecutorFieldConversion(unittest.TestCase):

    def test_success_result_upload_id_carries_through_and_error_is_none(self):
        provider = MockUploadProvider()
        upload_service = UploadService(provider_registry={"youtube": provider})
        executor = UploadExecutor(upload_service)
        job = make_job(platform="youtube")

        execution = executor.execute(job)
        raw_result = provider.upload(job.file_path, job.metadata)

        self.assertEqual(execution.upload_id, raw_result.upload_id)
        self.assertIsNone(execution.error)

    def test_failed_result_error_carries_through_and_upload_id_is_none(self):
        provider = MockUploadProvider(should_fail=True)
        upload_service = UploadService(provider_registry={"youtube": provider})
        executor = UploadExecutor(upload_service)
        job = make_job(platform="youtube")

        execution = executor.execute(job)

        self.assertEqual(execution.error, "Mock upload failed")
        self.assertIsNone(execution.upload_id)


if __name__ == "__main__":
    unittest.main()
