"""
Sprint115 - YouTube Upload Provider Foundation. Sprint108 UploadProvider
인터페이스를 구현하는 YouTubeUploadProvider 계약 테스트.

실제 YouTube API 호출/OAuth/Token은 전혀 다루지 않는다 - Sprint108
MockUploadProvider와 동일하게 결정적으로 성공/실패를 반환하는 stub
구현이며, platform="youtube"로 등록될 구체 클래스의 기반만 만든다.
upload_service.py/upload_executor.py는 이 스프린트에서 수정하지 않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.upload_provider import UploadProvider, UploadResult
from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider


SAMPLE_FILE_PATH = "output/20260716_120000/final/video.mp4"
SAMPLE_METADATA = {
    "title": "제목",
    "description": "설명",
    "hashtags": ["health"],
}


class TestYouTubeUploadProviderCreation(unittest.TestCase):

    def test_youtube_upload_provider_can_be_created(self):
        provider = YouTubeUploadProvider()
        self.assertIsInstance(provider, YouTubeUploadProvider)


class TestYouTubeUploadProviderContract(unittest.TestCase):

    def test_youtube_upload_provider_is_upload_provider(self):
        provider = YouTubeUploadProvider()
        self.assertIsInstance(provider, UploadProvider)


class TestYouTubeUploadProviderCallsUpload(unittest.TestCase):

    def test_upload_accepts_file_path_and_metadata_without_raising(self):
        provider = YouTubeUploadProvider()

        try:
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"YouTubeUploadProvider.upload() raised unexpectedly: {exc}")

        self.assertIsNotNone(result)


class TestYouTubeUploadProviderReturnsUploadResult(unittest.TestCase):

    def test_upload_returns_upload_result_instance(self):
        provider = YouTubeUploadProvider()

        result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertIsInstance(result, UploadResult)


class TestYouTubeUploadProviderMetadataPassthrough(unittest.TestCase):

    def test_upload_records_file_path_and_metadata_used(self):
        provider = YouTubeUploadProvider()

        provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertEqual(provider.last_file_path, SAMPLE_FILE_PATH)
        self.assertEqual(provider.last_metadata, SAMPLE_METADATA)
        self.assertIs(provider.last_metadata, SAMPLE_METADATA)


class TestYouTubeUploadProviderSuccessFailure(unittest.TestCase):

    def test_default_upload_succeeds_deterministically(self):
        provider = YouTubeUploadProvider()

        result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.upload_id)
        self.assertIsNone(result.error)

    def test_should_fail_flag_returns_failure_result(self):
        provider = YouTubeUploadProvider(should_fail=True)

        result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertFalse(result.success)
        self.assertIsNone(result.upload_id)
        self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main()
