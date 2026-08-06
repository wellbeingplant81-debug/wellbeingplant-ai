"""
Sprint76 - provider가 버리던 신호를 남기고, 같은 검색을 두 번 하지 않는다.

Pexels 사진 응답에는 alt(사진 설명)가 들어 있고 url에는 내용을 적은
슬러그가 있다. 순위를 매기는 데 쓸 수 있는 유일한 의미 정보인데
provider가 둘 다 버리고 있었다. 추가 API 호출은 없다 - 이미 받아 놓고
쓰지 않던 필드다.

검색 캐시는 별개다. asset_cache는 내려받은 파일을 캐시하지만 검색
응답은 캐시하지 않아, 같은 검색어가 매번 API를 다시 쳤다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers import pexels_provider
from app.services import search_cache


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


PHOTO_PAYLOAD = {
    "photos": [
        {
            "id": 123,
            "url": "https://www.pexels.com/photo/bowl-of-oatmeal-123/",
            "alt": "a white bowl of oatmeal topped with blueberries",
            "width": 1080,
            "height": 1920,
            "src": {"original": "https://images.pexels.com/a.jpg"},
        }
    ]
}

VIDEO_PAYLOAD = {
    "videos": [
        {
            "id": 77,
            "url": "https://www.pexels.com/video/water-poured-77/",
            "duration": 8,
            "video_files": [
                {"link": "https://v/a.mp4", "width": 1080, "height": 1920},
            ],
        }
    ]
}


class TestProviderKeepsTheSignal(unittest.TestCase):

    @patch.dict(os.environ, {"PEXELS_API_KEY": "k"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_photo_alt_is_kept(self, mock_get):
        mock_get.return_value = _Response(PHOTO_PAYLOAD)

        results = pexels_provider.search_photos("oatmeal")

        self.assertEqual(
            results[0]["alt"],
            "a white bowl of oatmeal topped with blueberries",
        )

    @patch.dict(os.environ, {"PEXELS_API_KEY": "k"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_photo_source_url_carries_the_slug(self, mock_get):
        mock_get.return_value = _Response(PHOTO_PAYLOAD)

        results = pexels_provider.search_photos("oatmeal")

        self.assertIn("bowl-of-oatmeal", results[0]["source_url"])

    @patch.dict(os.environ, {"PEXELS_API_KEY": "k"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_video_duration_is_kept(self, mock_get):
        mock_get.return_value = _Response(VIDEO_PAYLOAD)

        results = pexels_provider.search_videos("water")

        self.assertEqual(results[0]["duration"], 8)

    @patch.dict(os.environ, {"PEXELS_API_KEY": "k"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_a_missing_alt_is_an_empty_string_not_a_crash(self, mock_get):
        mock_get.return_value = _Response({"photos": [{
            "url": "https://www.pexels.com/photo/1/",
            "src": {"original": "https://images.pexels.com/a.jpg"},
        }]})

        results = pexels_provider.search_photos("x")

        self.assertEqual(results[0]["alt"], "")

    @patch.dict(os.environ, {"PEXELS_API_KEY": "k"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_the_existing_fields_are_unchanged(self, mock_get):
        mock_get.return_value = _Response(PHOTO_PAYLOAD)

        result = pexels_provider.search_photos("oatmeal")[0]

        self.assertEqual(result["source"], "pexels_image")
        self.assertEqual(result["download_url"], "https://images.pexels.com/a.jpg")
        self.assertEqual(result["width"], 1080)
        self.assertEqual(result["height"], 1920)
        self.assertEqual(result["query"], "oatmeal")


class TestSearchCache(unittest.TestCase):
    """같은 검색어로 두 번 부르지 않는다."""

    def setUp(self):
        search_cache.clear()
        self.addCleanup(search_cache.clear)

    def test_the_second_call_does_not_reach_the_provider(self):
        calls = []

        def provider(query):
            calls.append(query)
            return [{"source": "pexels_image", "alt": "x"}]

        first = search_cache.search("pexels_image", "oatmeal", provider)
        second = search_cache.search("pexels_image", "oatmeal", provider)

        self.assertEqual(calls, ["oatmeal"])
        self.assertEqual(first, second)

    def test_a_different_query_is_a_different_entry(self):
        calls = []

        def provider(query):
            calls.append(query)
            return []

        search_cache.search("pexels_image", "oatmeal", provider)
        search_cache.search("pexels_image", "granola", provider)

        self.assertEqual(calls, ["oatmeal", "granola"])

    def test_a_different_provider_is_a_different_entry(self):
        calls = []

        def provider(query):
            calls.append(query)
            return []

        search_cache.search("pexels_image", "oatmeal", provider)
        search_cache.search("pexels_video", "oatmeal", provider)

        self.assertEqual(len(calls), 2)

    def test_an_empty_result_is_still_cached(self):
        """0건도 결과다. 같은 검색어로 다시 물어도 0건이다."""

        calls = []

        def provider(query):
            calls.append(query)
            return []

        search_cache.search("pexels_image", "nothing", provider)
        search_cache.search("pexels_image", "nothing", provider)

        self.assertEqual(len(calls), 1)

    def test_a_failure_is_not_cached(self):
        """실패는 일시적일 수 있다. 캐시에 굳히면 그 실행 내내
        같은 provider가 죽은 것으로 남는다."""

        calls = []

        def provider(query):
            calls.append(query)
            raise Exception("network")

        for _ in range(2):
            with self.assertRaises(Exception):
                search_cache.search("pexels_image", "x", provider)

        self.assertEqual(len(calls), 2)

    def test_the_cached_list_cannot_be_mutated_by_a_caller(self):
        def provider(query):
            return [{"source": "pexels_image"}]

        first = search_cache.search("pexels_image", "q", provider)
        first.append({"injected": True})

        second = search_cache.search("pexels_image", "q", provider)

        self.assertEqual(len(second), 1)


if __name__ == "__main__":
    unittest.main()
