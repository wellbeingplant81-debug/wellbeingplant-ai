import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import subprompt_service


IMAGE_PROMPT = "Ultra realistic photo of a tired woman in a messy office."


def _mock_gemini_response(subprompts):
    response = MagicMock()
    response.text = json.dumps({"subprompts": subprompts}, ensure_ascii=False)
    return response


class TestGenerateSubprompts(unittest.TestCase):
    """
    Sprint62-5 - 하나의 image_prompt를 시각적으로 다른 4개의
    서브프롬프트로 분할한다. LLM 호출/파싱이 실패하면 예외를 삼키고
    image_prompt를 count번 반복한 리스트로 폴백한다 - 절대 파이프라인을
    막아서는 안 된다.
    """

    @patch("app.services.subprompt_service.client")
    def test_returns_four_subprompts_from_gemini_response(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["close-up shot, tired woman", "wide shot, messy office",
             "side angle, tired woman", "detail shot, cluttered desk"],
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], "close-up shot, tired woman")

    @patch("app.services.subprompt_service.client")
    def test_sends_image_prompt_to_gemini(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn(IMAGE_PROMPT, sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_strips_markdown_json_fence(self, mock_client):
        response = MagicMock()
        response.text = "```json\n" + json.dumps({"subprompts": ["a", "b", "c", "d"]}) + "\n```"
        mock_client.models.generate_content.return_value = response

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, ["a", "b", "c", "d"])

    @patch("app.services.subprompt_service.client")
    def test_falls_back_to_image_prompt_on_gemini_exception(self, mock_client):
        mock_client.models.generate_content.side_effect = Exception("quota exceeded")

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_falls_back_to_image_prompt_on_malformed_json(self, mock_client):
        response = MagicMock()
        response.text = "not json at all"
        mock_client.models.generate_content.return_value = response

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_falls_back_to_image_prompt_when_count_mismatch(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["only", "two"],
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_respects_custom_count(self, mock_client):
        mock_client.models.generate_content.side_effect = Exception("boom")

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT, count=2)

        self.assertEqual(result, [IMAGE_PROMPT] * 2)


class TestSubpromptShotTypeDiversity(unittest.TestCase):
    """
    Sprint63-1 - Visual Diversity 품질 향상. count가 기본값(4)일 때는
    Wide/Medium/Close-up/Detail Shot처럼 서로 다른 화면 구성을 명시적
    으로 요청해 중복 프롬프트를 줄인다. LLM이 지시를 무시하고 중복된
    서브프롬프트를 반환하면 안전망으로 image_prompt 반복 폴백을
    적용한다.
    """

    @patch("app.services.subprompt_service.client")
    def test_prompt_requests_four_distinct_shot_types(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"].lower()
        for shot_type in ["wide shot", "medium shot", "close-up", "detail shot"]:
            self.assertIn(shot_type, sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_prompt_instructs_against_duplicate_subprompts(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("중복", sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_falls_back_when_subprompts_contain_exact_duplicates(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["same framing", "same framing", "other", "another"],
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_falls_back_when_duplicates_differ_only_by_case_and_whitespace(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["Wide shot of a tired woman", "  wide shot of a tired woman  ",
             "close-up", "detail shot"],
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_accepts_four_distinct_subprompts_unchanged(self, mock_client):
        subprompts = [
            "Wide shot establishing the messy office.",
            "Medium shot of the tired woman at her desk.",
            "Close-up on her exhausted face.",
            "Detail shot of her cluttered desk items.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            subprompts,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)


if __name__ == "__main__":
    unittest.main()
