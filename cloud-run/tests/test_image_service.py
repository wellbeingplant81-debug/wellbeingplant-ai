import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.prompts.image_style import (
    MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT,
    MEDICAL_ILLUSTRATION_STYLE,
    WELLBEING_NEGATIVE_PROMPT,
    WELLBEING_STYLE,
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


class TestGenerateImageVisualTypeStyle(unittest.TestCase):
    """Sprint60 Hotfix - 문제1: visual_type="ai"인 scene은 사람/얼굴
    사진 스타일이 아니라 의료 일러스트/과학 시각화 스타일을 써야 한다."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.tmp_dir, "out.png")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_visual_type_ai_uses_medical_illustration_style(
        self, mock_client, mock_enhance,
    ):
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image(
            "microscopic view of gut bacteria",
            self.output_file,
            visual_type="ai",
        )

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertIn(MEDICAL_ILLUSTRATION_STYLE.strip(), kwargs["prompt"])
        self.assertEqual(
            kwargs["config"].negative_prompt, MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT,
        )

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_visual_type_ai_prompt_excludes_person_style_terms(
        self, mock_client, mock_enhance,
    ):
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image(
            "microscopic view of gut bacteria",
            self.output_file,
            visual_type="ai",
        )

        _, kwargs = mock_client.models.generate_images.call_args
        prompt_text = kwargs["prompt"]
        self.assertNotIn("Korean people", prompt_text)
        self.assertNotIn("Natural facial expression", prompt_text)
        self.assertNotIn("Correct human anatomy", prompt_text)
        self.assertNotIn("portrait photography", prompt_text)

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_visual_type_real_keeps_default_wellbeing_style(
        self, mock_client, mock_enhance,
    ):
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image(
            "a person drinking water in the morning",
            self.output_file,
            visual_type="real",
        )

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertIn(WELLBEING_STYLE.strip(), kwargs["prompt"])
        self.assertEqual(kwargs["config"].negative_prompt, WELLBEING_NEGATIVE_PROMPT)

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_visual_type_omitted_preserves_existing_default_behavior(
        self, mock_client, mock_enhance,
    ):
        # 기존 호출부(visual_type 인자를 아예 넘기지 않는 코드)가 계속
        # 예전과 동일하게 동작해야 한다 - 하위 호환성.
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image("a lifestyle scene", self.output_file)

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertIn(WELLBEING_STYLE.strip(), kwargs["prompt"])
        self.assertEqual(kwargs["config"].negative_prompt, WELLBEING_NEGATIVE_PROMPT)

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_is_thumbnail_takes_priority_over_visual_type_ai(
        self, mock_client, mock_enhance,
    ):
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image(
            "thumbnail prompt",
            self.output_file,
            is_thumbnail=True,
            visual_type="ai",
        )

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertNotIn(MEDICAL_ILLUSTRATION_STYLE.strip(), kwargs["prompt"])

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_visual_type_ai_hook_scene_still_uses_medical_style(
        self, mock_client, mock_enhance,
    ):
        # scene 1(hook)이 우연히 의료/세포 주제여도 사람 사진 스타일이
        # 아니라 의료 일러스트 스타일을 써야 한다.
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image(
            "cross-section of a blood vessel",
            self.output_file,
            is_hook_scene=True,
            visual_type="ai",
        )

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertIn(MEDICAL_ILLUSTRATION_STYLE.strip(), kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()
