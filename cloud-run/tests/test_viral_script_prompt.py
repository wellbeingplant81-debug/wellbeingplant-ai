import os
import sys
import unittest
from string import Template

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.prompts.image_prompt_rules import IMAGE_PROMPT_RULES
from app.prompts.viral_script_prompt import VIRAL_SCRIPT_PROMPT


RENDERED = VIRAL_SCRIPT_PROMPT.substitute(
    topic="밤에 화장실을 자주 가는 사람, 의외의 원인",
    target_duration=45,
    scene_count=6,
    target_chars=267,
    retry_feedback="",
)


class TestTemplateShape(unittest.TestCase):

    def test_is_string_template_instance(self):
        self.assertIsInstance(VIRAL_SCRIPT_PROMPT, Template)

    def test_substitutes_topic(self):
        self.assertIn("밤에 화장실을 자주 가는 사람, 의외의 원인", RENDERED)

    def test_substitutes_target_duration(self):
        self.assertIn("45초", RENDERED)

    def test_substitutes_scene_count(self):
        self.assertIn("정확히 6개", RENDERED)

    def test_requires_all_substitution_args(self):
        with self.assertRaises(KeyError):
            VIRAL_SCRIPT_PROMPT.substitute(topic="t")

    def test_substitutes_target_chars(self):
        self.assertIn("267", RENDERED)


class TestOutputSchemaUnchanged(unittest.TestCase):
    """Sprint51 must not change the JSON contract Sprint44-50 depend on."""

    def test_declares_required_top_level_keys(self):
        for key in ('"title"', '"hook"', '"script"', '"scenes"'):
            self.assertIn(key, RENDERED)

    def test_declares_required_scene_keys(self):
        for key in ('"scene"', '"narration"', '"image_prompt"'):
            self.assertIn(key, RENDERED)

    def test_ends_with_json_only_instruction(self):
        self.assertIn("JSON 외에는 아무것도 출력하지 마세요", RENDERED)


class TestReusesImagePromptRulesUnmodified(unittest.TestCase):

    def test_image_prompt_rules_embedded_verbatim(self):
        self.assertIn(IMAGE_PROMPT_RULES, RENDERED)


class TestHookFramework(unittest.TestCase):

    def test_contains_all_seven_hook_types(self):
        for hook_type in (
            "호기심 갭", "의외의 사실", "흔한 실수", "놓치면 후회",
            "의학적 오해", "숫자형", "전문가 화법",
        ):
            self.assertIn(hook_type, RENDERED)


class TestStoryFramework(unittest.TestCase):

    def test_contains_all_six_beats(self):
        for beat in ("Hook (0~3초)", "Question (3~8초)", "Reason", "Evidence", "Action", "CTA"):
            self.assertIn(beat, RENDERED)


class TestWritingRules(unittest.TestCase):

    def test_bans_generic_openers(self):
        for phrase in ("안녕하세요", "여러분", "따라서"):
            self.assertIn(phrase, RENDERED)

    def test_states_one_message_per_scene(self):
        self.assertIn("한 Scene당 하나의 메시지만", RENDERED)

    def test_states_no_repeated_information_rule(self):
        self.assertIn("반복하지 않는다", RENDERED)


class TestCtaFramework(unittest.TestCase):

    def test_contains_all_five_cta_styles(self):
        for style in ("저장형", "팔로우형", "공유형", "생활 습관 실천형", "병원 상담형"):
            self.assertIn(style, RENDERED)


class TestSafetyRules(unittest.TestCase):

    def test_bans_diagnostic_claims(self):
        self.assertIn("진단하지 않는다", RENDERED)

    def test_bans_absolute_claims(self):
        for word in ("무조건", "100%", "완치", "기적"):
            self.assertIn(word, RENDERED)

    def test_requires_medical_consultation_for_serious_symptoms(self):
        self.assertIn("전문의와 상담하세요", RENDERED)

    def test_bans_fabricated_statistics(self):
        self.assertIn("근거 없는 구체적 수치", RENDERED)


if __name__ == "__main__":
    unittest.main()
