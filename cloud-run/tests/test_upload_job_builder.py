"""
Sprint120 - Upload Pipeline Integration Intelligence. UploadJobBuilder
계약 테스트.

UploadJobBuilder는 개별 video output 값(video_id/file_path/platform/
title/description/hashtags)을 받아 Sprint109 UploadJob 모델(기존 구조
재사용, 신규 필드 추가 없음)을 조립한다. video_id/file_path/platform은
그대로 전달하고, title/description/hashtags는 UploadJob.metadata dict로
합성한다. 실제 pipeline 디렉터리 구조(output_path → 실제 파일 경로 추론)는
이 스프린트 범위 밖이다 - file_path는 호출자가 이미 완성된 값을
전달한다. upload_service.py/Provider/Factory/Registry/Bootstrap/Retry/
Distribution 기존 파일은 수정하지 않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.upload_job import UploadJob
from app.providers.upload.upload_provider import UploadResult
from app.services.upload_job_builder import UploadJobBuilder
from app.services.upload_provider_bootstrap import UploadProviderBootstrap


class TestUploadJobBuilderCreation(unittest.TestCase):

    def test_builder_can_be_created(self):
        builder = UploadJobBuilder()
        self.assertIsInstance(builder, UploadJobBuilder)


class TestUploadJobBuilderBuild(unittest.TestCase):

    def test_build_returns_upload_job_instance(self):
        builder = UploadJobBuilder()

        job = builder.build(
            video_id="20260716_120000",
            file_path="output/20260716_120000/video/final_short.mp4",
            platform="youtube",
            title="제목",
            description="설명",
            hashtags=["health"],
        )

        self.assertIsInstance(job, UploadJob)


class TestUploadJobBuilderVideoIdPassthrough(unittest.TestCase):

    def test_video_id_is_passed_through(self):
        builder = UploadJobBuilder()

        job = builder.build(
            video_id="20260716_120000",
            file_path="output/20260716_120000/video/final_short.mp4",
            platform="youtube",
            title="제목",
            description="설명",
            hashtags=["health"],
        )

        self.assertEqual(job.video_id, "20260716_120000")


class TestUploadJobBuilderFilePathPassthrough(unittest.TestCase):

    def test_file_path_is_passed_through(self):
        builder = UploadJobBuilder()

        job = builder.build(
            video_id="20260716_120000",
            file_path="output/20260716_120000/video/final_short.mp4",
            platform="youtube",
            title="제목",
            description="설명",
            hashtags=["health"],
        )

        self.assertEqual(job.file_path, "output/20260716_120000/video/final_short.mp4")


class TestUploadJobBuilderPlatformPassthrough(unittest.TestCase):

    def test_platform_is_passed_through(self):
        builder = UploadJobBuilder()

        job = builder.build(
            video_id="20260716_120000",
            file_path="output/20260716_120000/video/final_short.mp4",
            platform="youtube",
            title="제목",
            description="설명",
            hashtags=["health"],
        )

        self.assertEqual(job.platform, "youtube")


class TestUploadJobBuilderMetadataComposition(unittest.TestCase):

    def test_metadata_is_composed_from_title_description_hashtags(self):
        builder = UploadJobBuilder()

        job = builder.build(
            video_id="20260716_120000",
            file_path="output/20260716_120000/video/final_short.mp4",
            platform="youtube",
            title="제목",
            description="설명",
            hashtags=["health"],
        )

        self.assertEqual(
            job.metadata,
            {"title": "제목", "description": "설명", "hashtags": ["health"]},
        )


class TestUploadJobBuilderProducesProcessableJob(unittest.TestCase):

    def test_built_job_is_actually_processable_by_upload_service(self):
        builder = UploadJobBuilder()
        job = builder.build(
            video_id="20260716_120000",
            file_path="output/20260716_120000/video/final_short.mp4",
            platform="youtube",
            title="제목",
            description="설명",
            hashtags=["health"],
        )

        service = UploadProviderBootstrap().create_upload_service()
        result = service.upload(job)

        self.assertIsInstance(result, UploadResult)
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
