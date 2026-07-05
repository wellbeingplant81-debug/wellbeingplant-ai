import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_selector


PROMPT = "Ultra realistic photo of a tired woman in a messy office."


class TestAssetSelector(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.output_file = os.path.join(self._tmp_dir.name, "scene1.png")

    def _write_fake_cached_asset(self, content=b"fake bytes"):
        cached_path = os.path.join(self._tmp_dir.name, "cached_asset.jpg")
        with open(cached_path, "wb") as f:
            f.write(content)
        return cached_path, {"source": "pexels_video", "query": "tired woman"}

    @patch("app.services.asset_selector.generate_image")
    @patch("app.services.asset_selector.asset_cache.save_to_cache")
    @patch("app.services.asset_selector.asset_cache.get_cached", return_value=None)
    @patch("app.services.asset_selector._download", return_value=b"video bytes")
    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_first_provider_success_stops_chain(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_download,
        mock_get_cached,
        mock_save_to_cache,
        mock_generate_image,
    ):
        mock_pexels_video.return_value = [
            {"source": "pexels_video", "download_url": "video.mp4", "source_url": "u", "width": 1080, "height": 1920, "query": "tired woman"}
        ]

        cached_path = os.path.join(self._tmp_dir.name, "asset.mp4")
        with open(cached_path, "wb") as f:
            f.write(b"video bytes")
        mock_save_to_cache.return_value = cached_path

        result = asset_selector.select_asset(PROMPT, self.output_file)

        self.assertEqual(result["source"], "pexels_video")
        mock_pexels_photo.assert_not_called()
        mock_pixabay_video.assert_not_called()
        mock_pixabay_image.assert_not_called()
        mock_generate_image.assert_not_called()
        self.assertTrue(os.path.exists(self.output_file))
        with open(self.output_file, "rb") as f:
            self.assertEqual(f.read(), b"video bytes")

    @patch("app.services.asset_selector.generate_image")
    @patch("app.services.asset_selector.asset_cache.save_to_cache")
    @patch("app.services.asset_selector.asset_cache.get_cached", return_value=None)
    @patch("app.services.asset_selector._download", return_value=b"photo bytes")
    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_falls_through_when_first_provider_empty(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_download,
        mock_get_cached,
        mock_save_to_cache,
        mock_generate_image,
    ):
        mock_pexels_video.return_value = []
        mock_pexels_photo.return_value = [
            {"source": "pexels_image", "download_url": "photo.jpg", "source_url": "u", "width": 1080, "height": 1920, "query": "tired woman"}
        ]

        cached_path = os.path.join(self._tmp_dir.name, "asset.jpg")
        with open(cached_path, "wb") as f:
            f.write(b"photo bytes")
        mock_save_to_cache.return_value = cached_path

        result = asset_selector.select_asset(PROMPT, self.output_file)

        self.assertEqual(result["source"], "pexels_image")
        mock_pixabay_video.assert_not_called()
        mock_pixabay_image.assert_not_called()
        mock_generate_image.assert_not_called()

    @patch("app.services.asset_selector.generate_image")
    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", return_value=[])
    def test_falls_back_to_ai_image_when_all_empty(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_generate_image,
    ):
        mock_generate_image.return_value = self.output_file

        result = asset_selector.select_asset(PROMPT, self.output_file)

        self.assertEqual(result["source"], "ai_image")
        self.assertEqual(result["local_path"], self.output_file)
        mock_generate_image.assert_called_once()

    @patch("app.services.asset_selector.generate_image")
    @patch("app.providers.pixabay_provider.search_images", return_value=[])
    @patch("app.providers.pixabay_provider.search_videos", return_value=[])
    @patch("app.providers.pexels_provider.search_photos", return_value=[])
    @patch("app.providers.pexels_provider.search_videos", side_effect=Exception("network error"))
    def test_provider_exception_falls_through_to_next(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_generate_image,
    ):
        mock_generate_image.return_value = self.output_file

        result = asset_selector.select_asset(PROMPT, self.output_file)

        # pexels_video raised, but the chain should continue rather than crash
        self.assertEqual(result["source"], "ai_image")
        mock_pexels_photo.assert_called_once()

    @patch("app.services.asset_selector.generate_image")
    @patch("app.services.asset_selector._download")
    @patch("app.providers.pexels_provider.search_videos")
    def test_cached_asset_reused_without_download(
        self,
        mock_pexels_video,
        mock_download,
        mock_generate_image,
    ):
        mock_pexels_video.return_value = [
            {"source": "pexels_video", "download_url": "video.mp4", "source_url": "u", "width": 1080, "height": 1920, "query": "tired woman"}
        ]

        cached_path, meta = self._write_fake_cached_asset(b"cached bytes")

        with patch(
            "app.services.asset_selector.asset_cache.get_cached",
            return_value=(cached_path, meta),
        ):
            result = asset_selector.select_asset(PROMPT, self.output_file)

        mock_download.assert_not_called()
        self.assertEqual(result["source"], "pexels_video")
        with open(self.output_file, "rb") as f:
            self.assertEqual(f.read(), b"cached bytes")

    @patch("app.services.asset_selector.generate_image")
    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_empty_query_skips_search_and_uses_ai_fallback(
        self,
        mock_pexels_video,
        mock_pexels_photo,
        mock_pixabay_video,
        mock_pixabay_image,
        mock_generate_image,
    ):
        mock_generate_image.return_value = self.output_file

        # 전부 상투어라서 extract_search_query가 빈 문자열을 반환하는 프롬프트
        filler_only_prompt = "Ultra realistic, cinematic photography, no text, no watermark."

        result = asset_selector.select_asset(filler_only_prompt, self.output_file)

        mock_pexels_video.assert_not_called()
        mock_pexels_photo.assert_not_called()
        mock_pixabay_video.assert_not_called()
        mock_pixabay_image.assert_not_called()
        self.assertEqual(result["source"], "ai_image")


if __name__ == "__main__":
    unittest.main()
