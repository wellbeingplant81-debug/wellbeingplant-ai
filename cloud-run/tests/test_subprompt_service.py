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


class TestSubpromptSemanticFocusDiversity(unittest.TestCase):
    """
    Sprint63-2 - Shot Type뿐 아니라 의미적 초점(Environment/Subject/
    Action/Supporting Object)도 함께 다양화한다. LLM이 지시를
    무시하고 문자열이 겹치는 서브프롬프트를 반환하면 Sprint63-1의
    기존 중복 감지 폴백이 그대로 적용된다(새 감지 로직 추가 없음 -
    프롬프트 강화가 1차 방어선).
    """

    @patch("app.services.subprompt_service.client")
    def test_prompt_requests_four_distinct_focus_types(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"].lower()
        for focus_type in ["environment", "subject", "action", "supporting object"]:
            self.assertIn(focus_type, sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_prompt_pairs_each_shot_type_with_its_focus_type(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"].lower()
        expected_pairs = [
            ("wide shot", "environment"),
            ("medium shot", "subject"),
            ("close-up", "action"),
            ("detail shot", "supporting object"),
        ]
        for shot_type, focus_type in expected_pairs:
            # 같은 줄(같은 항목)에 shot type과 focus type이 함께
            # 나와야 LLM이 둘을 하나의 항목으로 묶어 이해할 수 있다.
            line = next(
                (l for l in sent_prompt.splitlines() if shot_type in l), None,
            )
            self.assertIsNotNone(line, f"'{shot_type}' 줄을 찾을 수 없습니다")
            self.assertIn(focus_type, line)

    @patch("app.services.subprompt_service.client")
    def test_prompt_instructs_against_semantic_repetition(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("의미", sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_still_falls_back_on_duplicate_subprompts(self, mock_client):
        # Sprint63-1 폴백 안전망이 Sprint63-2 프롬프트 강화 이후에도
        # 그대로 살아있어야 한다(회귀 금지).
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["same", "same", "other", "another"],
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_accepts_four_semantically_distinct_subprompts(self, mock_client):
        subprompts = [
            "Wide shot of the messy office, establishing the environment.",
            "Medium shot of the tired woman, the main subject, at her desk.",
            "Close-up on her hand rubbing her tired eyes, capturing the action.",
            "Detail shot of a cold coffee cup, a supporting object on the desk.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            subprompts,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)


class TestSubpromptVisualCompositionDiversity(unittest.TestCase):
    """
    Sprint63-3 - Shot Type/Semantic Focus에 더해 Camera angle,
    Composition, Subject distance까지 서로 겹치지 않도록 요청해
    시각적 다양성(Visual Composition)을 강화한다. 새로운 감지/폴백
    구조를 추가하지 않고 기존 prompt instruction만 확장한다 -
    Sprint63-1/63-2의 중복 감지·폴백 동작은 그대로 유지된다.
    """

    @patch("app.services.subprompt_service.client")
    def test_prompt_requests_four_distinct_camera_angles(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"].lower()
        for camera_angle in ["eye level", "low angle", "high angle", "over-the-shoulder"]:
            self.assertIn(camera_angle, sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_prompt_requests_four_distinct_compositions(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"].lower()
        for composition in ["centered", "rule of thirds", "foreground emphasis", "background emphasis"]:
            self.assertIn(composition, sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_prompt_requests_four_distinct_subject_distances(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"].lower()
        for distance in ["full body", "half body", "close detail", "wide environment"]:
            self.assertIn(distance, sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_each_numbered_item_bundles_all_composition_dimensions(self, mock_client):
        # 화면 구성 요소들이 서로 다른 줄에 흩어져 있으면 LLM이 어떤
        # shot에 어떤 camera angle/composition/distance가 짝지어지는지
        # 알기 어렵다 - 같은 줄(같은 항목)에 함께 나와야 한다.
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"].lower()
        first_item_line = next(
            l for l in sent_prompt.splitlines() if "wide shot" in l
        )
        self.assertIn("environment", first_item_line)
        self.assertTrue(
            any(angle in first_item_line for angle in
                ["eye level", "low angle", "high angle", "over-the-shoulder"]),
        )

    @patch("app.services.subprompt_service.client")
    def test_still_requests_shot_type_and_focus_type(self, mock_client):
        # Sprint63-1/63-2 지시가 Sprint63-3 확장 이후에도 그대로
        # 살아있어야 한다(회귀 금지).
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["a", "b", "c", "d"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"].lower()
        for shot_type in ["wide shot", "medium shot", "close-up", "detail shot"]:
            self.assertIn(shot_type, sent_prompt)
        for focus_type in ["environment", "subject", "action", "supporting object"]:
            self.assertIn(focus_type, sent_prompt)

    @patch("app.services.subprompt_service.client")
    def test_still_falls_back_on_duplicate_subprompts(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["same", "same", "other", "another"],
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_accepts_four_visually_distinct_subprompts(self, mock_client):
        subprompts = [
            "Wide shot, high angle, background emphasis, wide environment of the office.",
            "Medium shot, eye level, rule of thirds, half body of the tired woman.",
            "Close-up, low angle, foreground emphasis, close detail of her hand.",
            "Detail shot, over-the-shoulder, centered, full body view of the desk items.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            subprompts,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)


if __name__ == "__main__":
    unittest.main()
