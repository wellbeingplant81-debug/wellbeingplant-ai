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

# Sprint63-4 - Quality Gate가 요구하는 5개 축(Shot Type/Focus Type/
# Camera Angle/Composition/Subject Distance)을 전부 만족하는 기준
# fixture. 이전 스프린트(62-5~63-3)의 "accepts unchanged" 테스트들도
# 이 fixture로 갱신한다 - 기존 fixture는 새로 추가된 다양성 축(63-2/
# 63-3에서 도입된 focus/camera/composition/distance) 어휘가 전혀
# 없어 Quality Gate 도입 후에는 폴백을 유발하기 때문이다.
GOOD_SUBPROMPTS = [
    "Wide shot, eye level, centered, full body: the messy office environment at dawn.",
    "Medium shot, low angle, rule of thirds, half body: the subject, a tired woman, drinking coffee.",
    "Close-up, high angle, foreground emphasis, close detail: her action of rubbing tired eyes.",
    "Detail shot, over-the-shoulder, background emphasis, wide environment: a supporting object, an old alarm clock.",
]


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
            GOOD_SUBPROMPTS,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], GOOD_SUBPROMPTS[0])

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
        response.text = "```json\n" + json.dumps({"subprompts": GOOD_SUBPROMPTS}) + "\n```"
        mock_client.models.generate_content.return_value = response

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, GOOD_SUBPROMPTS)

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
            "Wide shot establishing the messy office, eye level, centered, full body, environment focus.",
            "Medium shot of the tired woman at her desk, low angle, rule of thirds, half body, subject focus.",
            "Close-up on her exhausted face, high angle, foreground emphasis, close detail, action focus.",
            "Detail shot of her cluttered desk items, over-the-shoulder, background emphasis, wide environment, supporting object focus.",
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
            "Wide shot of the messy office, establishing the environment, eye level, centered, full body.",
            "Medium shot of the tired woman, the main subject, at her desk, low angle, rule of thirds, half body.",
            "Close-up on her hand rubbing her tired eyes, capturing the action, high angle, foreground emphasis, close detail.",
            "Detail shot of a cold coffee cup, a supporting object on the desk, over-the-shoulder, background emphasis, wide environment.",
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


class TestSubpromptQualityGate(unittest.TestCase):
    """
    Sprint63-4 - 생성 품질 자동 검증(Quality Gate). Gemini가 반환한
    4개의 subprompt가 동일 문장/근사 중복 키워드/5개 다양성 축
    (Shot Type, Focus Type, Camera Angle, Composition, Subject
    Distance) 중 어느 하나라도 완전히 누락되면 기존 image_prompt
    반복 폴백을 그대로 사용한다. 새로운 재생성 로직은 추가하지
    않는다 - 단발성 검증 후 실패 시 즉시 폴백.
    """

    # --- 거의 동일한 키워드 반복 ---

    @patch("app.services.subprompt_service.client")
    def test_falls_back_when_subprompts_are_near_duplicate_in_wording(self, mock_client):
        # 정확히 동일하지는 않지만(기존 exact-duplicate 검사는 통과)
        # 단어 대부분이 겹치는 두 문장이 섞여 있으면 폴백해야 한다.
        mock_client.models.generate_content.return_value = _mock_gemini_response([
            "Wide shot of a tired woman sitting at a messy desk in the office.",
            "Wide shot of a tired woman sitting at a messy desk in an office.",
            "Close-up on her exhausted face, showing pure exhaustion in her eyes today.",
            "Detail shot of a coffee cup, cold and half-empty, sitting there quietly.",
        ])

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    # --- 다양성 축 누락 ---

    @patch("app.services.subprompt_service.client")
    def test_falls_back_when_shot_type_entirely_missing(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response([
            "Eye level, centered, full body: the messy office environment at dawn.",
            "Low angle, rule of thirds, half body: the subject, a tired woman, drinking coffee.",
            "High angle, foreground emphasis, close detail: her action of rubbing tired eyes.",
            "Over-the-shoulder, background emphasis, wide environment: a supporting object, an old alarm clock.",
        ])

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_falls_back_when_focus_type_entirely_missing(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response([
            "Wide shot, eye level, centered, full body: the messy office at dawn.",
            "Medium shot, low angle, rule of thirds, half body: a tired woman drinking coffee.",
            "Close-up, high angle, foreground emphasis, close detail: her rubbing tired eyes.",
            "Detail shot, over-the-shoulder, background emphasis, close detail: an old alarm clock.",
        ])

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_falls_back_when_camera_angle_entirely_missing(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response([
            "Wide shot, centered, full body: the messy office environment at dawn.",
            "Medium shot, rule of thirds, half body: the subject, a tired woman, drinking coffee.",
            "Close-up, foreground emphasis, close detail: her action of rubbing tired eyes.",
            "Detail shot, background emphasis, wide environment: a supporting object, an old alarm clock.",
        ])

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_falls_back_when_composition_entirely_missing(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response([
            "Wide shot, eye level, full body: the messy office environment at dawn.",
            "Medium shot, low angle, half body: the subject, a tired woman, drinking coffee.",
            "Close-up, high angle, close detail: her action of rubbing tired eyes.",
            "Detail shot, over-the-shoulder, wide environment: a supporting object, an old alarm clock.",
        ])

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_falls_back_when_subject_distance_entirely_missing(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response([
            "Wide shot, eye level, centered: the messy office environment at dawn.",
            "Medium shot, low angle, rule of thirds: the subject, a tired woman, drinking coffee.",
            "Close-up, high angle, foreground emphasis: her action of rubbing tired eyes.",
            "Detail shot, over-the-shoulder, background emphasis: a supporting object, an old alarm clock.",
        ])

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    # --- 동일 문장(기존 Sprint63-1 폴백 재확인) ---

    @patch("app.services.subprompt_service.client")
    def test_still_falls_back_on_identical_sentences(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS[:1] * 4,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    # --- 다양성 축 검사는 count가 4일 때만 적용 ---

    @patch("app.services.subprompt_service.client")
    def test_dimension_check_skipped_when_count_is_not_four(self, mock_client):
        # count=2일 때는 애초에 5개 축 키워드를 요청하지 않으므로
        # (_shot_type_instruction), 다양성 축 누락으로 폴백해서는
        # 안 된다 - 동일 문장/근사 중복만 아니면 그대로 반환한다.
        subprompts = ["A tired woman looking at her phone.", "A messy desk with papers scattered."]
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            subprompts,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT, count=2)

        self.assertEqual(result, subprompts)

    # --- 정상 케이스 ---

    @patch("app.services.subprompt_service.client")
    def test_passes_quality_gate_and_returns_unchanged_when_all_dimensions_present(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, GOOD_SUBPROMPTS)


class TestGenerateSubpromptsWithDiagnostics(unittest.TestCase):
    """
    Sprint73 - Subprompt Quality Gate Observability. 기존
    generate_subprompts()의 판정/폴백 값 자체는 전혀 바꾸지 않고,
    "왜" 폴백했는지(어느 게이트 조건이 실패했는지 + 그 시점의
    image_prompt 길이)를 별도로 조회할 수 있는
    generate_subprompts_with_diagnostics()를 추가한다. fallback_reason은
    Gemini 응답 자체의 문제(개수/중복/누락)와 예외성 오류(파싱/API)를
    구분하기 위한 고정된 코드 집합이다.
    """

    @patch("app.services.subprompt_service.client")
    def test_success_case_reports_no_fallback(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS,
        )

        subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT,
        )

        self.assertEqual(subprompts, GOOD_SUBPROMPTS)
        self.assertFalse(diagnostics["fallback_occurred"])
        self.assertIsNone(diagnostics["fallback_reason"])
        self.assertIsNone(diagnostics["fallback_detail"])

    @patch("app.services.subprompt_service.client")
    def test_count_mismatch_reports_correct_reason(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["only", "two"],
        )

        subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT,
        )

        self.assertEqual(subprompts, [IMAGE_PROMPT] * 4)
        self.assertTrue(diagnostics["fallback_occurred"])
        self.assertEqual(diagnostics["fallback_reason"], "count_mismatch")

    @patch("app.services.subprompt_service.client")
    def test_identical_sentences_reports_duplicate_reason(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS[:1] * 4,
        )

        _subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT,
        )

        self.assertEqual(diagnostics["fallback_reason"], "duplicate_subprompts")

    @patch("app.services.subprompt_service.client")
    def test_near_duplicate_wording_reports_correct_reason(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response([
            "Wide shot of a tired woman sitting at a messy desk in the office.",
            "Wide shot of a tired woman sitting at a messy desk in an office.",
            "Close-up on her exhausted face, showing pure exhaustion in her eyes today.",
            "Detail shot of a coffee cup, cold and half-empty, sitting there quietly.",
        ])

        _subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT,
        )

        self.assertEqual(diagnostics["fallback_reason"], "near_duplicate_keywords")

    @patch("app.services.subprompt_service.client")
    def test_missing_dimension_reports_correct_reason(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response([
            "Eye level, centered, full body: the messy office environment at dawn.",
            "Low angle, rule of thirds, half body: the subject, a tired woman, drinking coffee.",
            "High angle, foreground emphasis, close detail: her action of rubbing tired eyes.",
            "Over-the-shoulder, background emphasis, wide environment: a supporting object, an old alarm clock.",
        ])

        _subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT,
        )

        self.assertEqual(diagnostics["fallback_reason"], "missing_dimension")

    @patch("app.services.subprompt_service.client")
    def test_gemini_exception_reports_generation_error_reason(self, mock_client):
        mock_client.models.generate_content.side_effect = Exception("quota exceeded")

        _subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT,
        )

        self.assertEqual(diagnostics["fallback_reason"], "generation_error")
        self.assertIn("quota exceeded", diagnostics["fallback_detail"])

    @patch("app.services.subprompt_service.client")
    def test_malformed_json_reports_generation_error_reason(self, mock_client):
        response = MagicMock()
        response.text = "not json at all"
        mock_client.models.generate_content.return_value = response

        _subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT,
        )

        self.assertEqual(diagnostics["fallback_reason"], "generation_error")

    @patch("app.services.subprompt_service.client")
    def test_prompt_length_is_recorded_on_success(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS,
        )

        _subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT,
        )

        self.assertEqual(diagnostics["prompt_length"], len(IMAGE_PROMPT))

    @patch("app.services.subprompt_service.client")
    def test_prompt_length_is_recorded_on_fallback(self, mock_client):
        # Sprint73 - Visual Diversity Profile 등으로 image_prompt가
        # 길어진 경우와 Gemini 응답 자체 문제를 구분하려면, 폴백이
        # 발생했을 때도 그 시점의 실제 prompt 길이가 함께 기록돼야
        # 한다.
        mock_client.models.generate_content.side_effect = Exception("boom")
        long_prompt = IMAGE_PROMPT + " " + ("wide shot, low angle, rule of thirds, dramatic light. " * 3)

        _subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            long_prompt,
        )

        self.assertEqual(diagnostics["prompt_length"], len(long_prompt))
        self.assertGreater(diagnostics["prompt_length"], len(IMAGE_PROMPT))

    @patch("app.services.subprompt_service.client")
    def test_dimension_check_skip_for_non_default_count_reports_no_fallback(self, mock_client):
        subprompts_in = ["A tired woman looking at her phone.", "A messy desk with papers scattered."]
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            subprompts_in,
        )

        subprompts, diagnostics = subprompt_service.generate_subprompts_with_diagnostics(
            IMAGE_PROMPT, count=2,
        )

        self.assertEqual(subprompts, subprompts_in)
        self.assertFalse(diagnostics["fallback_occurred"])

    @patch("app.services.subprompt_service.client")
    def test_generate_subprompts_unaffected_by_diagnostics_addition(self, mock_client):
        # 요구사항: 기존 동작은 유지 - generate_subprompts()는 여전히
        # 순수 리스트만 반환해야 한다(튜플이 아님).
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertIsInstance(result, list)
        self.assertEqual(result, GOOD_SUBPROMPTS)


class TestGetLastDiagnosticsSideChannel(unittest.TestCase):
    """
    Sprint73 - generate_subprompts()(기존 공개 API, 이미 수십 개의
    호출부/테스트가 이 함수를 그대로 mock하고 있음)의 반환 타입은
    절대 바꾸지 않으면서, 방금 그 함수가 내부적으로 계산한 진단
    정보를 get_last_diagnostics()로 곁가지 조회할 수 있게 한다.
    generate_subprompts()를 그대로 mock하는 기존 테스트/호출부는
    이 side-channel이 채워지지 않아도(None) 정상 동작해야 한다.
    """

    def setUp(self):
        subprompt_service._diagnostics_state.last = None

    @patch("app.services.subprompt_service.client")
    def test_get_last_diagnostics_reflects_most_recent_call(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            ["only", "two"],
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        diagnostics = subprompt_service.get_last_diagnostics()

        self.assertTrue(diagnostics["fallback_occurred"])
        self.assertEqual(diagnostics["fallback_reason"], "count_mismatch")

    @patch("app.services.subprompt_service.client")
    def test_get_last_diagnostics_reflects_success(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS,
        )

        subprompt_service.generate_subprompts(IMAGE_PROMPT)

        diagnostics = subprompt_service.get_last_diagnostics()

        self.assertFalse(diagnostics["fallback_occurred"])

    def test_returns_none_when_never_called_in_this_thread(self):
        self.assertIsNone(subprompt_service.get_last_diagnostics())

    @patch("app.services.subprompt_service.client")
    def test_reset_diagnostics_clears_the_side_channel(self, mock_client):
        # 호출자(asset_integration_service._generate_extra_ai_assets)가
        # generate_subprompts()를 호출하기 직전에 리셋해두면, 그
        # 호출이 mock으로 가로채여 실제로 실행되지 않았을 때도(스레드
        # 로컬을 건드리지 않으므로) 이전 호출의 진단 정보가 남아있는
        # 것처럼 잘못 보이는 일이 없다.
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS,
        )
        subprompt_service.generate_subprompts(IMAGE_PROMPT)
        self.assertIsNotNone(subprompt_service.get_last_diagnostics())

        subprompt_service.reset_diagnostics()

        self.assertIsNone(subprompt_service.get_last_diagnostics())


class TestSubpromptQualityGateLanguageAliases(unittest.TestCase):
    """
    Sprint66-1 - Sprint65 실제 E2E("장내세균이 우울감과 기억력에
    영향을 주는 이유" scene4)에서 발견된 버그 재현/수정 확인. Gemini가
    focus/camera angle/composition/subject distance는 한국어+영어
    괄호 병기("환경(environment)")로 응답하면서 shot type만 한글
    음차("와이드 샷")로만 응답해, _has_missing_dimension()이 실제로는
    4개가 서로 다른 shot type이었음에도 "축 전체 누락"으로 오판해
    image_prompt 반복 폴백을 유발했다. 프롬프트 생성 로직
    (SHOT_TYPES/_shot_type_instruction)은 건드리지 않고, 검증 시
    한국어/자연어 alias를 함께 인정하도록 고친다.
    """

    # Sprint65 실제 quality_report 실패 로그에서 그대로 가져온 서브
    # 프롬프트 4개(장내세균 주제, scene4). shot type만 한글 음차,
    # 나머지 4축은 한국어+영어 괄호 병기.
    REAL_E2E_SUBPROMPTS = [
        "멸균 처리된 실험 장비와 커다란 창문으로 들어오는 부드러운 아침 햇살이 공존하는 미니멀한 "
        "실험실 전체를 아이 레벨(eye level)로 담아내는 와이드 샷. 화면 중앙(centered composition)에 "
        "선 연구원의 전신(full body)이 보이며, 그는 깨끗한 흰색 조리대 위에 놓인 페트리 접시를 응시하고 "
        "있음. 과학적 긴박함 속에서 환경(environment)이 주는 고요함과 집중의 순간을 포착.",
        "낮은 앵글(low angle)에서 3분할 구도(rule of thirds)로 포착한 미디엄 샷. 허리까지 보이는"
        "(half body) 연구원(subject)이 페트리 접시를 들고 있으며, 그의 얼굴에는 우려와 강렬한 집중이 "
        "교차함. 접시 안에서 공격적으로 퍼지는 어두운 박테리아 군집이 보이며, 세련된 웰니스 미학의 "
        "실험실 배경과 실험 램프의 거친 조명이 만드는 날카로운 그림자가 발견의 심각성을 강조.",
        "행위(action)에 초점을 맞춘 하이 앵글(high angle) 클로즈업 샷. 전경을 강조(foreground "
        "emphasis)하여 장갑을 낀 손이 금속 도구로 페트리 접시 안의 염증이 생긴 표면을 조심스럽게 건드리는 "
        "순간을 포착. 카메라가 어둡고 불건강해 보이는 박테리아가 공격적으로 퍼지는 아주 가까운 디테일"
        "(close detail)을 담아내며, 위에서 비추는 임상 조명이 유리에 거친 반사를 만들고 주변의 따뜻하고 "
        "깨끗한 작업 공간은 불안할 정도로 고요한 배경이 됨.",
        "연구원의 어깨 너머(over-the-shoulder)로 촬영한 디테일 샷. 전경의 페트리 접시(supporting "
        "object)에 담긴 위협적인 박테리아 군집이 상세하게 보이지만, 구도는 배경을 강조(background "
        "emphasis)하여 넓은 실험실 환경(wide environment)을 함께 보여줌. 배경에는 식물과 자연광이 있는 "
        "깨끗하고 미니멀한 미학이 드러나, 전경에 들고 있는 실험의 임상적 긴급성과 극명한 대조를 이루며 "
        "깊은 서사적 긴장감을 연출.",
    ]

    @patch("app.services.subprompt_service.client")
    def test_real_e2e_korean_shot_type_no_longer_falls_back(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            self.REAL_E2E_SUBPROMPTS,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, self.REAL_E2E_SUBPROMPTS)

    @patch("app.services.subprompt_service.client")
    def test_all_five_dimensions_expressed_only_in_korean_aliases(self, mock_client):
        subprompts = [
            "와이드 샷으로 환경을 담아낸 아이 레벨 화면 중앙 구도, 전신이 보이는 장면.",
            "미디엄 샷, 로우 앵글, 3분할 구도, 상반신이 보이는 피사체 장면.",
            "클로즈업 샷, 하이 앵글, 전경을 강조한 구도로 행동에 초점을 맞춘 근접 디테일 장면.",
            "디테일 샷, 오버 더 숄더, 배경을 강조한 구도로 소품과 넓은 배경이 함께 보이는 장면.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            subprompts,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)

    @patch("app.services.subprompt_service.client")
    def test_still_falls_back_when_dimension_truly_missing_in_any_language(self, mock_client):
        # shot type을 영어로도 한국어 alias로도 전혀 언급하지 않음 -
        # 진짜 누락은 여전히 잡아야 한다(회귀 확인).
        subprompts = [
            "환경(environment), 아이 레벨(eye level), 화면 중앙(centered), 전신(full body)만 있는 문장.",
            "피사체(subject), 로우 앵글(low angle), 3분할(rule of thirds), 상반신(half body)만 있는 문장.",
            "행동(action), 하이 앵글(high angle), 전경 강조(foreground emphasis), 근접 디테일(close detail)만 있는 문장.",
            "소품(supporting object), 오버 더 숄더(over-the-shoulder), 배경 강조(background emphasis), 넓은 환경(wide environment)만 있는 문장.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            subprompts,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_english_only_keywords_still_pass_unchanged(self, mock_client):
        # 기존 영어 키워드만 있는 경우(Sprint63-4 원래 동작)도 회귀 없이
        # 그대로 통과해야 한다.
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            GOOD_SUBPROMPTS,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, GOOD_SUBPROMPTS)


class TestSubpromptQualityGateEnglishParaphrases(unittest.TestCase):
    """
    Sprint67-2 - Sprint67-1 실제 E2E("혈관 나이를 되돌리는 방법" scene2)
    에서 발견된 버그 재현/수정 확인. Gemini가 영어로 응답하면서도
    canonical 키워드를 리터럴 그대로 쓰지 않고 하이픈 변형("eye-level")
    이나 자연스러운 패러프레이즈("exact center of the room", "left
    third of the frame", "emphasis on the background")를 쓰면
    _has_missing_dimension()이 오판했다. Sprint66-1의 한국어 alias는
    그대로 유지한 채, 하이픈/공백 정규화와 일부 영어 패러프레이즈
    alias를 추가한다.
    """

    # Sprint67-1 실제 quality_report 폴백 로그에서 그대로 가져온
    # 서브프롬프트 4개(혈관 나이 주제, scene2). shot type/focus/
    # subject distance는 우연히 다른 항목에서 커버됐지만, composition
    # (centered/rule of thirds/foreground emphasis/background emphasis)
    # 은 넷 다 리터럴로 전혀 매칭되지 않아 폴백을 유발했다.
    REAL_E2E_SUBPROMPTS = [
        "Eye-level wide shot of a minimalist, high-tech wellness clinic bathed in soft natural morning "
        "light. In the exact center of the room, a large, dark holographic screen displays the full "
        "length of a stylized, plaque-filled artery. This entire visualized artery glows with a "
        "dangerous red hue, creating a stark, cinematic focal point within the otherwise warm, clean, "
        "and peaceful environment.",
        "A dramatic low-angle medium shot focusing on a significant, curved section of the stylized "
        "artery, positioning it on the left third of the frame. This half-body view emphasizes the "
        "subject's formidable and unhealthy state, with the menacing red glow from the plaque buildup "
        "seeming to pulse with intensity. The dark, clinical background is slightly out of focus, "
        "drawing all attention to the stiff, diseased texture of the artery itself.",
        "High-angle close-up shot focusing on the action of blockage within the artery. A large, "
        "jagged formation of plaque, glowing an aggressive red, dominates the foreground, almost "
        "completely choking the arterial pathway. This view emphasizes the immediate danger, capturing "
        "the close detail of the stiff, straining vessel wall, while the surrounding medical "
        "visualization fades into a dark, cinematic void.",
        "An over-the-shoulder detail shot, where the camera's perspective is positioned just behind a "
        "small, isolated deposit of glowing red plaque (the supporting object). The focus is pulled "
        "towards the background, which reveals the vast, branching network of the wider arterial "
        "system stretching into the distance. This composition, with its emphasis on the background, "
        "contrasts the small, detailed problem in the foreground against the expansive, cleaner "
        "environment of the rest of the vessel, all within a warm, soft, wellness aesthetic.",
    ]

    @patch("app.services.subprompt_service.client")
    def test_real_sprint67_1_scene2_subprompts_no_longer_fall_back(self, mock_client):
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            self.REAL_E2E_SUBPROMPTS,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, self.REAL_E2E_SUBPROMPTS)

    @patch("app.services.subprompt_service.client")
    def test_hyphenated_camera_angles_match_space_canonical(self, mock_client):
        # over-the-shoulder를 일부러 빼서, eye-level/low-angle/high-angle
        # 하이픈 표기만으로 camera angle 축이 인정되는지 검증한다.
        subprompts = [
            "Wide shot, eye-level, centered, full body: the messy office environment at dawn.",
            "Medium shot, low-angle, rule of thirds, half body: the subject, a tired woman, "
            "drinking coffee.",
            "Close-up, high-angle, foreground emphasis, close detail: her action of rubbing "
            "tired eyes.",
            "Detail shot, background emphasis, wide environment: a supporting object, an old "
            "alarm clock.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(subprompts)

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)

    @patch("app.services.subprompt_service.client")
    def test_centered_via_center_paraphrase(self, mock_client):
        subprompts = [
            "Wide shot, eye level, full body: the messy office environment, exact center of the "
            "frame, at dawn.",
            "Medium shot, low angle, half body: the subject, a tired woman, drinking coffee.",
            "Close-up, high angle, close detail: her action of rubbing tired eyes.",
            "Detail shot, over-the-shoulder, wide environment: a supporting object, an old alarm "
            "clock.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(subprompts)

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)

    @patch("app.services.subprompt_service.client")
    def test_rule_of_thirds_via_third_of_the_frame_paraphrase(self, mock_client):
        subprompts = [
            "Wide shot, eye level, full body: the messy office environment at dawn.",
            "Medium shot, low angle, half body: the subject positioned on the left third of the "
            "frame, a tired woman, drinking coffee.",
            "Close-up, high angle, close detail: her action of rubbing tired eyes.",
            "Detail shot, over-the-shoulder, wide environment: a supporting object, an old alarm "
            "clock.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(subprompts)

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)

    @patch("app.services.subprompt_service.client")
    def test_foreground_emphasis_via_separated_words(self, mock_client):
        # "foreground"와 "emphasizes"가 서로 다른 문장에 떨어져 있어도
        # (실제 로그처럼) 인정되어야 한다.
        subprompts = [
            "Wide shot, eye level, full body: the messy office environment at dawn.",
            "Medium shot, low angle, half body: the subject, a tired woman, drinking coffee.",
            "Close-up, high angle, close detail: a cluttered desk item dominates the foreground. "
            "This view emphasizes the disorder of her life.",
            "Detail shot, over-the-shoulder, wide environment: a supporting object, an old alarm "
            "clock.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(subprompts)

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)

    @patch("app.services.subprompt_service.client")
    def test_background_emphasis_via_reordered_phrase(self, mock_client):
        subprompts = [
            "Wide shot, eye level, full body: the messy office environment at dawn.",
            "Medium shot, low angle, half body: the subject, a tired woman, drinking coffee.",
            "Close-up, high angle, close detail: her action of rubbing tired eyes.",
            "Detail shot, over-the-shoulder, wide environment: a supporting object, with emphasis "
            "on the background clutter.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(subprompts)

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, subprompts)

    @patch("app.services.subprompt_service.client")
    def test_still_falls_back_when_only_one_half_of_word_set_alias_present(self, mock_client):
        # "foreground"라는 단어는 있지만 "emphas-" 어근이 전체 텍스트
        # 어디에도 없으면 - 과도하게 느슨한 매칭이 되어서는 안 되므로
        # 여전히 폴백해야 한다(composition 축 전체 누락).
        subprompts = [
            "Wide shot, eye level, full body: the foreground of the messy office environment at "
            "dawn.",
            "Medium shot, low angle, half body: the subject, a tired woman, drinking coffee.",
            "Close-up, high angle, close detail: her action of rubbing tired eyes.",
            "Detail shot, over-the-shoulder, wide environment: a supporting object, an old alarm "
            "clock.",
        ]
        mock_client.models.generate_content.return_value = _mock_gemini_response(subprompts)

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, [IMAGE_PROMPT] * 4)

    @patch("app.services.subprompt_service.client")
    def test_korean_aliases_still_work_after_english_paraphrase_support_added(self, mock_client):
        # Sprint66-1 회귀 확인 - 실제 Sprint65 재현 케이스가 여전히
        # 통과해야 한다.
        real_sprint65_subprompts = (
            TestSubpromptQualityGateLanguageAliases.REAL_E2E_SUBPROMPTS
        )
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            real_sprint65_subprompts,
        )

        result = subprompt_service.generate_subprompts(IMAGE_PROMPT)

        self.assertEqual(result, real_sprint65_subprompts)


if __name__ == "__main__":
    unittest.main()
