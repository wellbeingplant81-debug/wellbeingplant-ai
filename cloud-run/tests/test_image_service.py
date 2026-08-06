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
    WELLBEING_NEGATIVE_PROMPT,
)
from app.services import image_service
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
            image_style=image_service.IMAGE_STYLE_MEDICAL,
        )

        _, kwargs = mock_client.models.generate_images.call_args
        # Sprint75 - 통짜 블록 대신 Style 슬롯으로 들어간다.
        self.assertIn("medical illustration", kwargs["prompt"])
        self.assertIn("scientific visualization", kwargs["prompt"])
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
            image_style=image_service.IMAGE_STYLE_MEDICAL,
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
            image_style=image_service.IMAGE_STYLE_DEFAULT,
        )

        _, kwargs = mock_client.models.generate_images.call_args
        # Sprint75 - 채널 스타일은 Style 슬롯에 들어간다. 인물 품질
        # 표현은 여기 없다 - 사물 scene에 사람을 요구하던 자리다.
        self.assertIn("editorial photography", kwargs["prompt"])
        self.assertNotIn("Korean people", kwargs["prompt"])
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
        self.assertIn("editorial photography", kwargs["prompt"])
        self.assertEqual(kwargs["config"].negative_prompt, WELLBEING_NEGATIVE_PROMPT)

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_thumbnail_style_wins_over_a_medical_prompt(
        self, mock_client, mock_enhance,
    ):
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image(
            "thumbnail prompt",
            self.output_file,
            image_style=image_service.IMAGE_STYLE_THUMBNAIL,
        )

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertNotIn("medical illustration", kwargs["prompt"])

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
            image_style=image_service.IMAGE_STYLE_MEDICAL,
        )

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertIn("medical illustration", kwargs["prompt"])
        self.assertNotIn("Korean people", kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()


class TestOnlyOneImageIsRequested(unittest.TestCase):
    """Sprint74 - 파이프라인은 이미지를 4장씩 만들고 3장을 버리고 있었다.

    generate_image()는 number_of_images를 지정하지 않았고, 그러면 Vertex가
    자기 기본값을 적용한다. 그 기본값이 4다. 코드는
    generated_images[0]만 저장하므로 나머지 세 장은 만들어지고 요금이
    청구된 뒤 그대로 버려졌다.

    Sprint74 실측에서 드러났다. Best-of-N OFF/ON을 비교하려고 Imagen
    호출을 세었더니 OFF 팔이 요청 7번에 이미지 28장(정확히 4배)을
    받았고, 디스크에 쓰인 것은 7장이었다. 요청 장수를 명시한 ON 팔은
    6번 요청에 14장이었다 - 후보를 2장씩 뽑았는데도 절반이었다.

    scene당 4장이 필요한 적은 없었다. 필요한 것은 명시적으로 요청한다.
    """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.tmp_dir, "out.png")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_a_single_image_request_asks_for_exactly_one(
        self, mock_client, mock_enhance,
    ):
        mock_client.models.generate_images.return_value = _mock_response()

        generate_image("a bowl of oatmeal", self.output_file)

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertEqual(kwargs["config"].number_of_images, 1)

    @patch("app.services.image_service.enhance_image")
    @patch("app.services.image_service.client")
    def test_a_candidate_request_asks_for_exactly_that_many(
        self, mock_client, mock_enhance,
    ):
        response = _mock_response()
        response.generated_images = response.generated_images * 3
        mock_client.models.generate_images.return_value = response

        image_service.generate_image_candidates(
            "a bowl of oatmeal",
            [os.path.join(self.tmp_dir, f"c{i}.png") for i in range(3)],
        )

        _, kwargs = mock_client.models.generate_images.call_args
        self.assertEqual(kwargs["config"].number_of_images, 3)
