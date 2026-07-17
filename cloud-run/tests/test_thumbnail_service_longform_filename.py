"""
Sprint123 (GREEN) - create_thumbnail()이 render_profile에 따라 출력
파일명을 분기한다 (Shorts: thumbnail.png 그대로, Longform:
thumbnail_longform.png).
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


LONGFORM = RenderProfile.get("longform")


class TestCreateThumbnailLongformFilename(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    @patch("app.services.thumbnail_service.generate_image")
    def test_default_uses_existing_filename(self, mock_generate_image):
        output = create_thumbnail("title", "topic", self.project_path)

        self.assertEqual(os.path.basename(output), "thumbnail.png")
        args, _ = mock_generate_image.call_args
        self.assertEqual(os.path.basename(args[1]), "thumbnail.png")

    @patch("app.services.thumbnail_service.generate_image")
    def test_longform_uses_distinct_filename(self, mock_generate_image):
        output = create_thumbnail(
            "title", "topic", self.project_path, render_profile=LONGFORM,
        )

        self.assertEqual(os.path.basename(output), "thumbnail_longform.png")
        args, _ = mock_generate_image.call_args
        self.assertEqual(os.path.basename(args[1]), "thumbnail_longform.png")


if __name__ == "__main__":
    unittest.main()
