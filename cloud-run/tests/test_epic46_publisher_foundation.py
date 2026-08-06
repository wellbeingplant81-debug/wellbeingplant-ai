"""
Epic 46 Sprint 001 (RED) - Publisher Foundation.

app/providers/upload/(Sprint108-119, 기존 Distribution Upload Provider
아키텍처)를 Epic 46의 공식 구현으로 그대로 확장한다 - app/publisher/
같은 새 병렬 디렉터리/중복 Factory/중복 Protocol을 만들지 않는다
(사용자 명시적 지시).

이번 Sprint에서 유일하게 새로 필요한 것은 UploadRequest뿐이다 -
UploadProvider.upload(file_path, metadata)의 기존 시그니처는 바꾸지
않는다(15개 이상의 기존 호출부/테스트에 영향을 주는 Breaking Change를
피하기 위해 - Regression Zero/기존 Production 코드 영향 금지).
UploadRequest는 file_path/metadata를 하나로 묶어 전달하고 싶을 때
쓸 수 있는 추가적인 값 객체다.

실제 YouTube API/OAuth/Playlist/Thumbnail/Analytics/UI는 다루지 않는다.

아직 UploadRequest 구현이 없으므로(RED) 관련 테스트는 실패해야 정상 -
나머지(UploadResult/PublisherProtocol/MockPublisher/Factory)는 기존
구현을 그대로 재사용/재확인하는 회귀 성격의 테스트다.
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
from app.providers.upload.upload_provider import UploadProvider, UploadResult
from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider

SAMPLE_FILE_PATH = "output/20260716_120000/final/video.mp4"
SAMPLE_METADATA = {"title": "제목", "description": "설명", "hashtags": ["health"]}


class TestUploadRequestCreation(unittest.TestCase):

    def test_upload_request_holds_file_path_and_metadata(self):
        from app.providers.upload.upload_request import UploadRequest

        request = UploadRequest(file_path=SAMPLE_FILE_PATH, metadata=SAMPLE_METADATA)

        self.assertEqual(request.file_path, SAMPLE_FILE_PATH)
        self.assertEqual(request.metadata, SAMPLE_METADATA)

    def test_upload_request_metadata_defaults_to_empty_dict(self):
        from app.providers.upload.upload_request import UploadRequest

        request = UploadRequest(file_path=SAMPLE_FILE_PATH)

        self.assertEqual(request.metadata, {})

    def test_upload_request_does_not_change_upload_provider_signature(self):
        # Epic46의 핵심 제약 - 기존 upload(file_path, metadata) 시그니처는
        # UploadRequest 도입 후에도 그대로 동작해야 한다(회귀 없음).
        provider = MockUploadProvider()
        result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)
        self.assertTrue(result.success)


class TestUploadResultCreation(unittest.TestCase):

    def test_upload_result_success_case(self):
        result = UploadResult(
            success=True, upload_id="abc", url="https://x", error=None
        )

        self.assertTrue(result.success)
        self.assertEqual(result.upload_id, "abc")
        self.assertEqual(result.url, "https://x")
        self.assertIsNone(result.error)

    def test_upload_result_failure_case(self):
        result = UploadResult(success=False, upload_id=None, url=None, error="boom")

        self.assertFalse(result.success)
        self.assertEqual(result.error, "boom")


class TestPublisherProtocolImplementation(unittest.TestCase):

    def test_upload_provider_is_abstract_base(self):
        with self.assertRaises(TypeError):
            UploadProvider()

    def test_mock_provider_implements_protocol(self):
        self.assertIsInstance(MockUploadProvider(), UploadProvider)

    def test_youtube_provider_implements_protocol(self):
        self.assertIsInstance(YouTubeUploadProvider(), UploadProvider)


class TestMockPublisherUpload(unittest.TestCase):

    def test_mock_publisher_upload_success(self):
        from app.providers.upload.upload_request import UploadRequest

        request = UploadRequest(file_path=SAMPLE_FILE_PATH, metadata=SAMPLE_METADATA)
        provider = MockUploadProvider()

        result = provider.upload(request.file_path, request.metadata)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.upload_id)
        self.assertIsNotNone(result.url)
        self.assertIsNone(result.error)

    def test_mock_publisher_upload_failure(self):
        from app.providers.upload.upload_request import UploadRequest

        request = UploadRequest(file_path=SAMPLE_FILE_PATH, metadata=SAMPLE_METADATA)
        provider = MockUploadProvider(should_fail=True)

        result = provider.upload(request.file_path, request.metadata)

        self.assertFalse(result.success)
        self.assertIsNone(result.upload_id)
        self.assertIsNotNone(result.error)


class TestFactoryReturnsMockPublisher(unittest.TestCase):

    def test_factory_create_mock_returns_mock_upload_provider(self):
        factory = UploadProviderFactory()

        provider = factory.create("mock")

        self.assertIsInstance(provider, MockUploadProvider)


if __name__ == "__main__":
    unittest.main()
