"""
Sprint97 (RED) - Script Intelligence 강화. 현재 활성 템플릿인
SCRIPT_PROMPT(ENABLE_VIRAL_WRITER=False가 기본값이라 실제 운영에서
쓰이는 쪽)에 임상 경험이 풍부한 의학 전문가 + 100만 구독자 유튜브
크리에이터 페르소나와 작성 지침을 시스템 프롬프트로 추가한다. JSON
스키마/Scene 1 규칙/이미지 프롬프트 규칙 등 기존 계약은 전혀 바꾸지
않는다. 아직 구현이 없으므로(RED) 모든 테스트는 실패해야 정상이다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.prompts.script_prompt import SCRIPT_PROMPT


RENDERED = SCRIPT_PROMPT.substitute(
    topic="고혈압을 방치하면 생기는 일",
    target_duration=55,
    scene_count=6,
    target_chars=296,
    retry_feedback="",
)


class TestScriptPromptPersona(unittest.TestCase):

    def test_declares_clinical_expert_persona(self):
        self.assertIn("임상 경험이 풍부한 의학 전문가", RENDERED)

    def test_declares_million_subscriber_creator_persona(self):
        self.assertIn("100만", RENDERED)
        self.assertIn("구독자", RENDERED)

    def test_requires_latest_medical_evidence(self):
        self.assertIn("최신 의학적 근거", RENDERED)

    def test_requires_plain_language_for_lay_audience(self):
        self.assertIn("일반인이 이해할 수 있도록", RENDERED)

    def test_requires_explaining_why_not_just_listing(self):
        self.assertIn("왜 그런지", RENDERED)

    def test_declares_hook_to_action_flow(self):
        for stage in ("Hook", "원인", "기전", "위험성", "예방법", "실천법"):
            self.assertIn(stage, RENDERED)

    def test_requires_high_information_density(self):
        self.assertIn("정보 밀도", RENDERED)

    def test_forbids_exaggeration_and_unfounded_certainty(self):
        self.assertIn("과장", RENDERED)
        self.assertIn("단정적", RENDERED)

    def test_requires_matching_production_profile_length(self):
        self.assertIn("영상 길이", RENDERED)


class TestExistingContractUnchanged(unittest.TestCase):
    """페르소나 추가가 기존 JSON 스키마/Scene 규칙을 깨서는 안 된다."""

    def test_still_declares_required_top_level_keys(self):
        for key in ('"title"', '"hook"', '"script"', '"scenes"'):
            self.assertIn(key, RENDERED)

    def test_still_declares_required_scene_keys(self):
        for key in ('"scene"', '"narration"', '"image_prompt"'):
            self.assertIn(key, RENDERED)

    def test_still_substitutes_topic_and_duration(self):
        self.assertIn("고혈압을 방치하면 생기는 일", RENDERED)
        self.assertIn("55초", RENDERED)

    def test_still_ends_with_json_only_instruction(self):
        self.assertIn("JSON 외에는 아무것도 출력하지 마세요", RENDERED)


if __name__ == "__main__":
    unittest.main()
