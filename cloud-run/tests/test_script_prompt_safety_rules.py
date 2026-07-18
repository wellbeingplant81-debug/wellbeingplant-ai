"""
Sprint150 (RED) - 실사용 경로(SCRIPT_PROMPT, ENABLE_VIRAL_WRITER=False일
때 쓰이는 쪽) 안전 지시문 강화. viral_script_prompt.py의 안전 규칙 4개
(진단 금지/통계 조작 금지/과장·단정 금지+금지어/전문의 상담 필수)를
문구 그대로 이식한다. 기존 계약(JSON 스키마/치환 변수/23번째 줄 문장/
Viral Writer 전용 섹션 미포함)은 전혀 바꾸지 않는다. 아직 구현이
없으므로(RED) 모든 신규 테스트는 실패해야 정상이다.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.prompts.script_prompt import SCRIPT_PROMPT
from app.services import script_service


RENDERED = SCRIPT_PROMPT.substitute(
    topic="고혈압을 방치하면 생기는 일",
    target_duration=55,
    scene_count=6,
    target_chars=296,
    retry_feedback="",
)


class TestSafetyRules(unittest.TestCase):

    def test_bans_diagnostic_claims(self):
        self.assertIn("진단하지 않는다", RENDERED)

    def test_bans_absolute_claims(self):
        for word in ("무조건", "100%", "완치", "즉시 낫는다", "기적"):
            self.assertIn(word, RENDERED)

    def test_requires_medical_consultation_for_serious_symptoms(self):
        self.assertIn("전문의와 상담하세요", RENDERED)

    def test_bans_fabricated_statistics(self):
        self.assertIn("근거 없는 구체적 수치", RENDERED)


class TestExistingContractStillUnchanged(unittest.TestCase):
    """Sprint150이 기존 계약을 깨서는 안 된다."""

    def test_still_forbids_exaggeration_line_present(self):
        # test_script_prompt_persona.py의 기존 테스트와 동일한 문구 -
        # 23번째 줄을 삭제/수정하지 않았음을 재확인.
        self.assertIn("과장", RENDERED)
        self.assertIn("단정적", RENDERED)

    def test_does_not_leak_viral_writer_only_sections(self):
        # test_script_service_viral_writer.py의
        # test_flag_off_uses_legacy_script_prompt가 이미 규정한 계약을
        # 프롬프트 콘텐츠 레벨에서 재확인 - Hook 프레임워크/글쓰기
        # 철학은 Sprint132/134 범위이며 이번 스프린트에서 절대
        # 포함하지 않는다.
        self.assertNotIn("Hook 프레임워크", RENDERED)
        self.assertNotIn("글쓰기 철학", RENDERED)


def _mock_gemini_response():
    response = MagicMock()
    response.text = json.dumps(
        {
            "title": "t",
            "hook": "h",
            "script": "s",
            "scenes": [
                {"scene": 1, "narration": "n1", "image_prompt": "p1"},
            ],
        },
        ensure_ascii=False,
    )
    return response


class TestSafetyRulesReachGeminiViaScriptService(unittest.TestCase):
    """
    Sprint150 승인 조건 - Template 문자열 검사만으로는 부족하다.
    script_service.generate_script()를 실제로 호출해(client만 mock),
    Gemini에게 진짜로 전달되는 최종 렌더링 Prompt(call_args.kwargs
    ["contents"])에 안전 규칙 4개가 전부 포함되는지 검증한다. 최종
    Render Prompt 기준.
    """

    def _sent_prompt(self, **kwargs):
        with patch("app.services.script_service.client") as mock_client, \
             patch("app.services.script_service.config.ENABLE_VIRAL_WRITER", False):
            mock_client.models.generate_content.return_value = _mock_gemini_response()

            script_service.generate_script(topic="고혈압을 방치하면 생기는 일", **kwargs)

            return mock_client.models.generate_content.call_args.kwargs["contents"]

    def test_final_rendered_prompt_contains_all_safety_rules(self):
        sent_prompt = self._sent_prompt(target_duration=55, scene_count=6)

        self.assertIn("진단하지 않는다", sent_prompt)
        self.assertIn("근거 없는 구체적 수치", sent_prompt)
        for word in ("무조건", "100%", "완치", "즉시 낫는다", "기적"):
            self.assertIn(word, sent_prompt)
        self.assertIn("전문의와 상담하세요", sent_prompt)

    def test_final_rendered_prompt_still_excludes_viral_only_sections(self):
        sent_prompt = self._sent_prompt(target_duration=55, scene_count=6)

        self.assertNotIn("Hook 프레임워크", sent_prompt)
        self.assertNotIn("글쓰기 철학", sent_prompt)


if __name__ == "__main__":
    unittest.main()
