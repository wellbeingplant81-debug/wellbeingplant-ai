"""
Sprint122 (RED) - create_thumbnail()이 render_profile(기본값 None)을
받으면 render_profile["thumbnail_aspect_ratio"]를 generate_image()에
aspect_ratio kwarg로 전달한다. 안 넘기면 기존과 동일하게 aspect_ratio
kwarg 자체를 추가하지 않는다(image_service.generate_image()의 기본값
"9:16"이 그대로 적용됨).
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.thumbnail_service import create_thumbnail
from app.services.render_profile import RenderProfile


class TestCreateThumbnailRenderProfile(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    @patch("app.services.thumbnail_service.generate_image")
    def test_longform_render_profile_passes_16_9_aspect_ratio(self, mock_generate_image):
        longform = RenderProfile.get("longform")

        create_thumbnail(
            "title", "topic", self.project_path, render_profile=longform,
        )

        _, kwargs = mock_generate_image.call_args
        self.assertEqual(kwargs["aspect_ratio"], "16:9")

    @patch("app.services.thumbnail_service.generate_image")
    def test_no_render_profile_omits_aspect_ratio_kwarg(self, mock_generate_image):
        create_thumbnail("title", "topic", self.project_path)

        _, kwargs = mock_generate_image.call_args
        self.assertNotIn("aspect_ratio", kwargs)


if __name__ == "__main__":
    unittest.main()
