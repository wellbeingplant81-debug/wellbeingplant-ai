"""
Sprint104 - Video Distribution Intelligence. PlatformAdapter 공통
인터페이스 + YouTubeAdapter/InstagramAdapter/TikTokAdapter 3개 Mock
구현. 실제 API 호출은 플랫폼별 ENABLE_{PLATFORM}_REAL_API 플래그(전부
기본 False) 뒤에 있어, 이 테스트에서는 네트워크 호출이 절대 없다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.services import platform_adapter


SAMPLE_QUEUE_ITEM = {
    "video_id": "20260715_120000",
    "output_path": "output/20260715_120000",
    "title": "제목",
    "description": "설명",
    "hashtags": ["health"],
    "thumbnail_path": "output/20260715_120000/thumbnail.png",
    "target_platforms": ["youtube"],
}


class TestPlatformAdapterInterface(unittest.TestCase):

    def test_platform_adapter_is_abstract(self):
        with self.assertRaises(TypeError):
            platform_adapter.PlatformAdapter()

    def test_publish_result_has_expected_fields(self):
        result = platform_adapter.PublishResult(
            success=True, platform_post_id="abc", error=None,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.platform_post_id, "abc")
        self.assertIsNone(result.error)


class _MockRealApiFlagTestCase(unittest.TestCase):
    """공통 setUp: 각 real-api 플래그를 원래 값으로 되돌린다."""

    flag_name = None

    def setUp(self):
        original = getattr(config, self.flag_name)
        self.addCleanup(setattr, config, self.flag_name, original)


class TestYouTubeAdapterMock(_MockRealApiFlagTestCase):

    flag_name = "ENABLE_YOUTUBE_REAL_API"

    def test_mock_publish_succeeds_deterministically(self):
        config.ENABLE_YOUTUBE_REAL_API = False

        adapter = platform_adapter.YouTubeAdapter()
        result = adapter.publish(SAMPLE_QUEUE_ITEM)

        self.assertIsInstance(result, platform_adapter.PublishResult)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.platform_post_id)
        self.assertIsNone(result.error)

    def test_real_api_flag_on_does_not_call_real_api(self):
        # Sprint104 원칙: 실제 API 호출 금지. 플래그가 켜져 있어도
        # 이번 스프린트에는 실제 구현이 없으므로 네트워크를 타지 않고
        # 명시적으로 미구현임을 알리는 예외를 던져야 한다(조용히 mock
        # 결과를 반환해 "진짜 연동된 것처럼" 보이면 안 된다).
        config.ENABLE_YOUTUBE_REAL_API = True

        adapter = platform_adapter.YouTubeAdapter()
        with self.assertRaises(NotImplementedError):
            adapter.publish(SAMPLE_QUEUE_ITEM)


class TestInstagramAdapterMock(_MockRealApiFlagTestCase):

    flag_name = "ENABLE_INSTAGRAM_REAL_API"

    def test_mock_publish_succeeds_deterministically(self):
        config.ENABLE_INSTAGRAM_REAL_API = False

        adapter = platform_adapter.InstagramAdapter()
        result = adapter.publish(SAMPLE_QUEUE_ITEM)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.platform_post_id)

    def test_real_api_flag_on_does_not_call_real_api(self):
        config.ENABLE_INSTAGRAM_REAL_API = True

        adapter = platform_adapter.InstagramAdapter()
        with self.assertRaises(NotImplementedError):
            adapter.publish(SAMPLE_QUEUE_ITEM)


class TestTikTokAdapterMock(_MockRealApiFlagTestCase):

    flag_name = "ENABLE_TIKTOK_REAL_API"

    def test_mock_publish_succeeds_deterministically(self):
        config.ENABLE_TIKTOK_REAL_API = False

        adapter = platform_adapter.TikTokAdapter()
        result = adapter.publish(SAMPLE_QUEUE_ITEM)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.platform_post_id)

    def test_real_api_flag_on_does_not_call_real_api(self):
        config.ENABLE_TIKTOK_REAL_API = True

        adapter = platform_adapter.TikTokAdapter()
        with self.assertRaises(NotImplementedError):
            adapter.publish(SAMPLE_QUEUE_ITEM)


class TestGetAdapterRegistry(unittest.TestCase):

    def test_get_adapter_returns_correct_type_per_platform(self):
        self.assertIsInstance(
            platform_adapter.get_adapter("youtube"), platform_adapter.YouTubeAdapter,
        )
        self.assertIsInstance(
            platform_adapter.get_adapter("instagram"), platform_adapter.InstagramAdapter,
        )
        self.assertIsInstance(
            platform_adapter.get_adapter("tiktok"), platform_adapter.TikTokAdapter,
        )

    def test_get_adapter_raises_for_unknown_platform(self):
        with self.assertRaises(ValueError):
            platform_adapter.get_adapter("facebook")


if __name__ == "__main__":
    unittest.main()
