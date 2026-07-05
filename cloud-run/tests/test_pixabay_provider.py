import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers import pixabay_provider


def _fake_response(status_code=200, json_data=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.text = text
    return response


class TestHasApiKey(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_false_when_not_set(self):
        self.assertFalse(pixabay_provider.has_api_key())

    @patch.dict(os.environ, {"PIXABAY_API_KEY": "test-key"})
    def test_returns_true_when_set(self):
        self.assertTrue(pixabay_provider.has_api_key())


class TestPixabayProvider(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises(self):
        with self.assertRaises(Exception):
            pixabay_provider.search_images("tired woman")

    @patch.dict(os.environ, {"PIXABAY_API_KEY": "test-key"})
    @patch("app.providers.pixabay_provider.requests.get")
    def test_search_images_normalizes_results(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={
                "hits": [
                    {
                        "pageURL": "https://pixabay.com/photo/1",
                        "largeImageURL": "https://pixabay.com/1_large.jpg",
                        "imageWidth": 1080,
                        "imageHeight": 1920,
                    }
                ]
            },
        )

        results = pixabay_provider.search_images("tired woman")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "pixabay_image")
        self.assertEqual(results[0]["download_url"], "https://pixabay.com/1_large.jpg")

    @patch.dict(os.environ, {"PIXABAY_API_KEY": "test-key"})
    @patch("app.providers.pixabay_provider.requests.get")
    def test_search_videos_picks_highest_resolution_variant(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={
                "hits": [
                    {
                        "pageURL": "https://pixabay.com/video/1",
                        "videos": {
                            "tiny": {"url": "tiny.mp4", "width": 320, "height": 180},
                            "large": {"url": "large.mp4", "width": 1920, "height": 1080},
                        },
                    }
                ]
            },
        )

        results = pixabay_provider.search_videos("tired woman")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "pixabay_video")
        self.assertEqual(results[0]["download_url"], "large.mp4")

    @patch.dict(os.environ, {"PIXABAY_API_KEY": "test-key"})
    @patch("app.providers.pixabay_provider.requests.get")
    def test_per_page_enforces_minimum_of_three(self, mock_get):
        mock_get.return_value = _fake_response(json_data={"hits": []})

        pixabay_provider.search_images("tired woman", per_page=1)

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["per_page"], 3)

    @patch.dict(os.environ, {"PIXABAY_API_KEY": "test-key"})
    @patch("app.providers.pixabay_provider.requests.get")
    def test_non_200_status_raises(self, mock_get):
        mock_get.return_value = _fake_response(status_code=400, text="Bad Request")

        with self.assertRaises(Exception):
            pixabay_provider.search_images("tired woman")

    @patch.dict(os.environ, {"PIXABAY_API_KEY": "test-key"})
    @patch("app.providers.pixabay_provider.requests.get")
    def test_hit_without_videos_skipped(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={"hits": [{"pageURL": "https://pixabay.com/video/2", "videos": {}}]},
        )

        results = pixabay_provider.search_videos("tired woman")

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
