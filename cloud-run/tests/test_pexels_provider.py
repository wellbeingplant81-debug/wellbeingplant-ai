import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers import pexels_provider


def _fake_response(status_code=200, json_data=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.text = text
    return response


class TestHasApiKey(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_false_when_not_set(self):
        self.assertFalse(pexels_provider.has_api_key())

    @patch.dict(os.environ, {"PEXELS_API_KEY": "test-key"})
    def test_returns_true_when_set(self):
        self.assertTrue(pexels_provider.has_api_key())


class TestPexelsProvider(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises(self):
        with self.assertRaises(Exception):
            pexels_provider.search_photos("tired woman")

    @patch.dict(os.environ, {"PEXELS_API_KEY": "test-key"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_search_photos_normalizes_results(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={
                "photos": [
                    {
                        "url": "https://pexels.com/photo/1",
                        "width": 1080,
                        "height": 1920,
                        "src": {"original": "https://images.pexels.com/1.jpg"},
                    }
                ]
            },
        )

        results = pexels_provider.search_photos("tired woman")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "pexels_image")
        self.assertEqual(results[0]["download_url"], "https://images.pexels.com/1.jpg")
        self.assertEqual(results[0]["width"], 1080)
        self.assertEqual(results[0]["query"], "tired woman")

    @patch.dict(os.environ, {"PEXELS_API_KEY": "test-key"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_search_videos_picks_highest_resolution_file(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={
                "videos": [
                    {
                        "url": "https://pexels.com/video/1",
                        "video_files": [
                            {"link": "low.mp4", "width": 360, "height": 640},
                            {"link": "high.mp4", "width": 1080, "height": 1920},
                        ],
                    }
                ]
            },
        )

        results = pexels_provider.search_videos("tired woman")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "pexels_video")
        self.assertEqual(results[0]["download_url"], "high.mp4")

    @patch.dict(os.environ, {"PEXELS_API_KEY": "test-key"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_non_200_status_raises(self, mock_get):
        mock_get.return_value = _fake_response(status_code=401, text="Unauthorized")

        with self.assertRaises(Exception):
            pexels_provider.search_photos("tired woman")

    @patch.dict(os.environ, {"PEXELS_API_KEY": "test-key"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_empty_results_returns_empty_list(self, mock_get):
        mock_get.return_value = _fake_response(json_data={"photos": []})

        results = pexels_provider.search_photos("nonexistent query xyz")

        self.assertEqual(results, [])

    @patch.dict(os.environ, {"PEXELS_API_KEY": "test-key"})
    @patch("app.providers.pexels_provider.requests.get")
    def test_video_without_files_skipped(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={"videos": [{"url": "https://pexels.com/video/2", "video_files": []}]},
        )

        results = pexels_provider.search_videos("tired woman")

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
