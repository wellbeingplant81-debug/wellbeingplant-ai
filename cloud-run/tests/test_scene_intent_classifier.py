"""
Sprint101 - Video Intent Intelligence. scene_intent_classifier.
classify_video_intent()가

1. 정상 응답을 VideoIntent(source="ai_classifier")로 올바르게
   변환하는지
2. Gemini 호출 자체가 실패해도 예외를 밖으로 던지지 않고 안전한
   기본값(FALLBACK_INTENT, source="rule")으로 폴백하는지
3. 구조화 응답 파싱이 실패(response.parsed is None)해도 동일하게
   폴백하는지
4. 응답은 왔지만 confidence가 너무 낮으면(MIN_CONFIDENCE_THRESHOLD
   미만) 원래 intent를 쓰지 않고 폴백하되, reason에 원래 판정을
   남기는지

를 확인한다. 실제 Gemini API 호출은 전혀 하지 않는다(client.models.
generate_content를 mock).
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from pydantic import ValidationError

from app.models.video_intent import VideoIntentAssessment
from app.prompts.video_intent_rubric import VIDEO_INTENT_RUBRIC
from app.services import scene_intent_classifier as svc


class TestClassifyVideoIntentSuccess(unittest.TestCase):

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_normal_response_maps_to_ai_classifier_source(self, mock_generate):
        mock_response = MagicMock()
        mock_response.parsed = VideoIntentAssessment(
            intent="preferred_video",
            confidence=0.9,
            reason="운동 동작이 핵심이라 video가 더 자연스러움",
        )
        mock_generate.return_value = mock_response

        result = svc.classify_video_intent("운동하는 장면", "a woman exercising")

        self.assertEqual(result.intent, "preferred_video")
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.source, "ai_classifier")
        self.assertIn("운동", result.reason)

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_optional_scene_role_and_intent_do_not_break_call(self, mock_generate):
        mock_response = MagicMock()
        mock_response.parsed = VideoIntentAssessment(
            intent="required_image", confidence=1.0, reason="해부학 도해",
        )
        mock_generate.return_value = mock_response

        result = svc.classify_video_intent(
            "혈관 설명", "a blood vessel diagram",
            scene_role="explanation", scene_intent="medical",
        )

        self.assertEqual(result.intent, "required_image")
        self.assertEqual(result.source, "ai_classifier")


class TestClassifyVideoIntentFallback(unittest.TestCase):

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_gemini_call_exception_falls_back_safely(self, mock_generate):
        mock_generate.side_effect = Exception("network timeout")

        result = svc.classify_video_intent("아무 장면", "any prompt")

        self.assertEqual(result.intent, svc.FALLBACK_INTENT)
        self.assertEqual(result.source, "rule")
        self.assertIn("Gemini unavailable", result.reason)
        self.assertIn("network timeout", result.reason)

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_missing_parsed_response_falls_back_safely(self, mock_generate):
        mock_response = MagicMock()
        mock_response.parsed = None
        mock_generate.return_value = mock_response

        result = svc.classify_video_intent("아무 장면", "any prompt")

        self.assertEqual(result.intent, svc.FALLBACK_INTENT)
        self.assertEqual(result.source, "rule")
        self.assertIn("Gemini unavailable", result.reason)

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_malformed_response_raising_during_parse_falls_back_safely(self, mock_generate):
        # response.parsed 자체에 접근할 때 예외가 나는 상황(SDK 파싱
        # 실패)을 흉내낸다.
        mock_response = MagicMock()
        type(mock_response).parsed = property(
            lambda self: (_ for _ in ()).throw(ValueError("malformed json"))
        )
        mock_generate.return_value = mock_response

        result = svc.classify_video_intent("아무 장면", "any prompt")

        self.assertEqual(result.intent, svc.FALLBACK_INTENT)
        self.assertEqual(result.source, "rule")
        self.assertIn("malformed json", result.reason)

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_low_confidence_falls_back_but_keeps_original_in_reason(self, mock_generate):
        mock_response = MagicMock()
        mock_response.parsed = VideoIntentAssessment(
            intent="required_video", confidence=0.2, reason="애매한 장면",
        )
        mock_generate.return_value = mock_response

        result = svc.classify_video_intent("애매한 장면", "an ambiguous prompt")

        self.assertEqual(result.intent, svc.FALLBACK_INTENT)
        self.assertEqual(result.source, "rule")
        self.assertIn("Low confidence", result.reason)
        self.assertIn("required_video", result.reason)  # 원래 판정도 기록됨

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_missing_required_field_raises_validation_error_and_falls_back(
        self, mock_generate,
    ):
        # Gemini가 intent/confidence/reason 중 일부를 빠뜨린 JSON을
        # 반환하면, VideoIntentAssessment 생성 자체가 pydantic
        # ValidationError를 던진다 - 이것도 안전하게 폴백해야 한다.
        mock_response = MagicMock()

        def _raise_validation_error():
            raise ValidationError.from_exception_data(
                "VideoIntentAssessment",
                [{"type": "missing", "loc": ("confidence",), "input": {}}],
            )

        type(mock_response).parsed = property(lambda self: _raise_validation_error())
        mock_generate.return_value = mock_response

        result = svc.classify_video_intent("아무 장면", "any prompt")

        self.assertEqual(result.intent, svc.FALLBACK_INTENT)
        self.assertEqual(result.source, "rule")
        self.assertIn("Gemini unavailable", result.reason)

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_calls_generate_content_with_video_intent_rubric(self, mock_generate):
        mock_response = MagicMock()
        mock_response.parsed = VideoIntentAssessment(
            intent="preferred_image", confidence=0.8, reason="ok",
        )
        mock_generate.return_value = mock_response

        svc.classify_video_intent("나레이션", "image prompt")

        _, kwargs = mock_generate.call_args
        contents = kwargs.get("contents") or mock_generate.call_args[0][0]
        self.assertIn(VIDEO_INTENT_RUBRIC, contents)

    @patch("app.services.scene_intent_classifier.client.models.generate_content")
    def test_confidence_exactly_at_threshold_is_not_fallback(self, mock_generate):
        mock_response = MagicMock()
        mock_response.parsed = VideoIntentAssessment(
            intent="preferred_video",
            confidence=svc.MIN_CONFIDENCE_THRESHOLD,
            reason="경계값",
        )
        mock_generate.return_value = mock_response

        result = svc.classify_video_intent("경계 장면", "borderline prompt")

        self.assertEqual(result.intent, "preferred_video")
        self.assertEqual(result.source, "ai_classifier")


if __name__ == "__main__":
    unittest.main()
