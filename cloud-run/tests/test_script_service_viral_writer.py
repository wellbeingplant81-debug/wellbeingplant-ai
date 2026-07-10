import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import script_service


FAKE_RESPONSE_DATA = {
    "title": "t",
    "hook": "h",
    "script": "s",
    "scenes": [
        {"scene": 1, "narration": "n1", "image_prompt": "p1"},
    ],
}


def _mock_gemini_response():
    response = MagicMock()
    response.text = json.dumps(FAKE_RESPONSE_DATA, ensure_ascii=False)
    return response


class TestViralWriterFlagTemplateSelection(unittest.TestCase):

    def test_flag_off_uses_legacy_script_prompt(self):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", False):
            mock_client.models.generate_content.return_value = _mock_gemini_response()

            script_service.generate_script(topic="주제")

            sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
            self.assertNotIn("Hook 프레임워크", sent_prompt)
            self.assertNotIn("글쓰기 철학", sent_prompt)

    def test_flag_on_uses_viral_script_prompt(self):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", True):
            mock_client.models.generate_content.return_value = _mock_gemini_response()

            script_service.generate_script(topic="주제")

            sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
            self.assertIn("Hook 프레임워크", sent_prompt)
            self.assertIn("글쓰기 철학", sent_prompt)

    def test_flag_off_prompt_still_contains_topic_and_schema(self):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", False):
            mock_client.models.generate_content.return_value = _mock_gemini_response()

            script_service.generate_script(topic="밤에 화장실 자주 가는 이유")

            sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
            self.assertIn("밤에 화장실 자주 가는 이유", sent_prompt)
            self.assertIn('"scenes"', sent_prompt)

    def test_flag_on_prompt_still_contains_topic_and_schema(self):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", True):
            mock_client.models.generate_content.return_value = _mock_gemini_response()

            script_service.generate_script(topic="밤에 화장실 자주 가는 이유")

            sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
            self.assertIn("밤에 화장실 자주 가는 이유", sent_prompt)
            self.assertIn('"scenes"', sent_prompt)


class TestOutputParsingUnaffectedByFlag(unittest.TestCase):
    """The flag must only change which prompt is sent - parsing/return shape
    must stay identical either way (no API-breaking change)."""

    def _run(self, flag_value):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", flag_value):
            mock_client.models.generate_content.return_value = _mock_gemini_response()
            return script_service.generate_script(
                topic="주제", target_duration=45, scene_count=6,
            )

    def test_flag_off_returns_expected_shape(self):
        result = self._run(False)
        self.assertEqual(result, {"success": True, "data": FAKE_RESPONSE_DATA})

    def test_flag_on_returns_expected_shape(self):
        result = self._run(True)
        self.assertEqual(result, {"success": True, "data": FAKE_RESPONSE_DATA})

    def test_flag_on_still_strips_markdown_json_fences(self):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", True):
            response = MagicMock()
            response.text = "```json\n" + json.dumps(FAKE_RESPONSE_DATA, ensure_ascii=False) + "\n```"
            mock_client.models.generate_content.return_value = response

            result = script_service.generate_script(topic="주제")

            self.assertEqual(result["data"], FAKE_RESPONSE_DATA)

    def test_default_flag_value_is_false(self):
        """Regression guard: Sprint51 must ship OFF by default."""
        from app import config
        self.assertFalse(config.ENABLE_VIRAL_WRITER)


class TestSubstitutionArgsPassedThroughRegardlessOfFlag(unittest.TestCase):

    def test_custom_duration_and_scene_count_reach_the_prompt(self):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", True):
            mock_client.models.generate_content.return_value = _mock_gemini_response()

            script_service.generate_script(
                topic="주제", target_duration=30, scene_count=4,
            )

            sent_prompt = mock_client.models.generate_content.call_args.kwargs["contents"]
            self.assertIn("30초", sent_prompt)
            self.assertIn("정확히 4개", sent_prompt)


class TestTargetCharsAndRetryFeedback(unittest.TestCase):
    """Sprint69-2 - Duration Gate Adaptive Retry. Writer 프롬프트에
    목표 글자 수를 명시하고, 재시도 시 직전 estimated_seconds 기반
    피드백을 주입한다. 두 템플릿(SCRIPT_PROMPT/VIRAL_SCRIPT_PROMPT)
    모두에 적용되므로 플래그 on/off 양쪽에서 검증한다."""

    def _sent_prompt(self, flag_value, **kwargs):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", flag_value):
            mock_client.models.generate_content.return_value = _mock_gemini_response()

            script_service.generate_script(topic="주제", **kwargs)

            return mock_client.models.generate_content.call_args.kwargs["contents"]

    def test_prompt_includes_target_chars_derived_from_default_duration(self):
        # DEFAULT_CHARS_PER_SECOND(5.93) * 45초 ≈ 267자.
        for flag in (False, True):
            sent_prompt = self._sent_prompt(flag, target_duration=45)
            self.assertIn("267", sent_prompt)

    def test_target_chars_scales_with_target_duration(self):
        # 5.93 * 30 ≈ 178자.
        for flag in (False, True):
            sent_prompt = self._sent_prompt(flag, target_duration=30)
            self.assertIn("178", sent_prompt)

    def test_no_retry_feedback_by_default(self):
        for flag in (False, True):
            sent_prompt = self._sent_prompt(flag)
            self.assertNotIn("재시도 피드백", sent_prompt)

    def test_retry_feedback_is_injected_when_provided(self):
        for flag in (False, True):
            sent_prompt = self._sent_prompt(
                flag, retry_feedback="[재시도 피드백] 테스트 피드백 문구입니다.",
            )
            self.assertIn("[재시도 피드백] 테스트 피드백 문구입니다.", sent_prompt)


if __name__ == "__main__":
    unittest.main()
