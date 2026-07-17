"""
Sprint122/123 (GREEN, Stock 크롭 Hotfix) - build_provider_chain()의
image_orientation은 Stock Image/Video provider(Pexels/Pixabay) 모두에
적용된다(Sprint123 item 6 - Longform은 Stock Video로 채워진 Scene도
landscape 원본이어야 크롭이 안 생긴다). 기본값 None은 각 provider
자신의 기본값과 완전히 하위 호환이다.

Pexels는 "landscape"/"portrait" 값을 쓰지만 Pixabay는 "horizontal"/
"vertical"을 쓴다 - Sprint122에서 Pixabay에도 "landscape"를 그대로
전달한 것은 실제 버그였다(Pixabay API가 이해하지 못하는 값). 이
파일은 그 버그 수정도 함께 검증한다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.provider_factory import build_provider_chain


class TestProviderFactoryOrientation(unittest.TestCase):

    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pexels_provider.search_photos")
    @patch("app.providers.pixabay_provider.search_videos")
    @patch("app.providers.pexels_provider.search_videos")
    def test_default_orientation_omits_kwarg_and_uses_provider_defaults(
        self, mock_pexels_videos, mock_pixabay_videos, mock_pexels_photos, mock_pixabay_images,
    ):
        # image_orientation을 안 넘기면(기본값 None) 4개 provider 호출
        # 전부 orientation kwarg 자체가 없다 - 각자의 기본값("portrait"/
        # "vertical")이 그대로 적용되는 기존 동작과 완전히 동일하다.
        for mock in (mock_pexels_videos, mock_pixabay_videos, mock_pexels_photos, mock_pixabay_images):
            mock.return_value = []

        chain = build_provider_chain()
        by_source = dict(chain)

        for source in by_source:
            by_source[source]("query")

        mock_pexels_videos.assert_called_once_with("query")
        mock_pixabay_videos.assert_called_once_with("query")
        mock_pexels_photos.assert_called_once_with("query")
        mock_pixabay_images.assert_called_once_with("query")

    @patch("app.providers.pixabay_provider.search_images")
    @patch("app.providers.pexels_provider.search_photos")
    def test_landscape_orientation_used_for_pexels_image(
        self, mock_pexels_photos, mock_pixabay_images,
    ):
        mock_pexels_photos.return_value = []
        mock_pixabay_images.return_value = []

        chain = build_provider_chain(image_orientation="landscape")
        by_source = dict(chain)

        by_source["pexels_image"]("query")

        mock_pexels_photos.assert_called_once_with("query", orientation="landscape")

    @patch("app.providers.pixabay_provider.search_images")
    def test_landscape_orientation_translated_to_horizontal_for_pixabay_image(
        self, mock_pixabay_images,
    ):
        mock_pixabay_images.return_value = []

        chain = build_provider_chain(image_orientation="landscape")
        by_source = dict(chain)

        by_source["pixabay_image"]("query")

        mock_pixabay_images.assert_called_once_with("query", orientation="horizontal")

    @patch("app.providers.pexels_provider.search_videos")
    def test_landscape_orientation_used_for_pexels_video(self, mock_pexels_videos):
        mock_pexels_videos.return_value = []

        chain = build_provider_chain(image_orientation="landscape")
        by_source = dict(chain)

        by_source["pexels_video"]("query")

        mock_pexels_videos.assert_called_once_with("query", orientation="landscape")

    @patch("app.providers.pixabay_provider.search_videos")
    def test_landscape_orientation_translated_to_horizontal_for_pixabay_video(
        self, mock_pixabay_videos,
    ):
        mock_pixabay_videos.return_value = []

        chain = build_provider_chain(image_orientation="landscape")
        by_source = dict(chain)

        by_source["pixabay_video"]("query")

        mock_pixabay_videos.assert_called_once_with("query", orientation="horizontal")

    @patch("app.providers.pixabay_provider.search_videos")
    def test_portrait_orientation_translated_to_vertical_for_pixabay_video(
        self, mock_pixabay_videos,
    ):
        mock_pixabay_videos.return_value = []

        chain = build_provider_chain(image_orientation="portrait")
        by_source = dict(chain)

        by_source["pixabay_video"]("query")

        mock_pixabay_videos.assert_called_once_with("query", orientation="vertical")


if __name__ == "__main__":
    unittest.main()
