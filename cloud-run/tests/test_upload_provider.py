"""
Sprint108 - Distribution Upload Provider Foundation. 실제 플랫폼 업로드
전 Provider 추상화 계층(UploadProvider 인터페이스 + MockUploadProvider)의
계약(contract) 테스트.

Sprint104의 platform_adapter.PlatformAdapter(distribution 큐 아이템을
받아 발행 상태를 판단하는 상위 계층)와는 다른, 더 낮은 레벨의 추상화다:
UploadProvider는 큐/발행 판단과 무관하게 "파일 하나를 업로드한다"는
행위 자체만 추상화한다. 이 스프린트에서는 실제 플랫폼 API, OAuth,
Token, Scheduler, Queue 연결을 전혀 다루지 않는다 - Interface와
Mock 구현만 검증한다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.upload_provider import UploadProvider, UploadResult
from app.providers.upload.mock_upload_provider import MockUploadProvider


SAMPLE_FILE_PATH = "output/20260716_120000/final/video.mp4"
SAMPLE_METADATA = {
    "title": "제목",
    "description": "설명",
    "hashtags": ["health"],
}


class TestUploadProviderInterface(unittest.TestCase):

    def test_upload_provider_is_abstract(self):
        with self.assertRaises(TypeError):
            UploadProvider()

    def test_upload_result_has_expected_fields(self):
        result = UploadResult(
            success=True, upload_id="abc", url="https://example.com/abc", error=None,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.upload_id, "abc")
        self.assertEqual(result.url, "https://example.com/abc")
        self.assertIsNone(result.error)


class TestMockUploadProviderContract(unittest.TestCase):

    def test_mock_upload_provider_is_upload_provider(self):
        provider = MockUploadProvider()
        self.assertIsInstance(provider, UploadProvider)

    def test_mock_upload_returns_upload_result_instance(self):
        provider = MockUploadProvider()
        result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)
        self.assertIsInstance(result, UploadResult)

    def test_mock_upload_succeeds_deterministically(self):
        provider = MockUploadProvider()
        result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.upload_id)
        self.assertIsNone(result.error)

    def test_mock_upload_never_performs_real_network_call(self):
        # Sprint108 범위 - 실제 플랫폼 API/OAuth/Token은 이 스프린트에서
        # 다루지 않는다. Mock은 항상 결정적으로 성공만 반환해야 하고,
        # 네트워크 관련 예외를 던져서는 안 된다.
        provider = MockUploadProvider()
        try:
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"MockUploadProvider.upload() raised unexpectedly: {exc}")
        self.assertTrue(result.success)

    def test_mock_upload_does_not_require_real_file_to_exist(self):
        # Mock 단계에서는 실제 파일 존재 여부를 검증하지 않는다 -
        # 파일 시스템/네트워크 의존 없이 순수하게 계약만 검증한다.
        provider = MockUploadProvider()
        result = provider.upload("nonexistent/path.mp4", SAMPLE_METADATA)
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
