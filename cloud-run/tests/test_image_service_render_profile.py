"""
Sprint122 (RED) - image_service.generate_image()이 aspect_ratio를
파라미터로 받는다(기본값 "9:16" - 오늘의 하드코딩 값과 동일해
호출부가 안 넘기면 100% 기존 동작). Longform 경로(asset_integration_
service/thumbnail_service)가 render_profile의 image_aspect_ratio/
thumbnail_aspect_ratio를 여기로 흘려보낸다.
"""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.image_service import generate_image


def _mock_response():
    image = MagicMock()
    image.image_bytes = b"fake png bytes"
    generated = MagicMock()
    generated.image = image
    response = MagicMock()
    response.generated_images = [generated]
    return response


class TestGenerateImageAspectRatioParam(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.tmp_dir, "out.png")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_default_aspect_ratio_is_9_16(self, mock_client, mock_enhance):
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image("a lifestyle scene", self.output_file)

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertEqual(kwargs["config"].aspect_ratio, "9:16")

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_explicit_aspect_ratio_is_used(self, mock_client, mock_enhance):
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image(
            "a wide landscape scene", self.output_file, aspect_ratio="16:9",
        )

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertEqual(kwargs["config"].aspect_ratio, "16:9")


if __name__ == "__main__":
    unittest.main()
