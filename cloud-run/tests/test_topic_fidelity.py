"""
Sprint95 - Topic Fidelity (Epic 48).

착수 계기는 "아침 공복 물"로 시킨 영상이 "커피" 영상으로 나온
사례였다. 그런데 그 프로젝트에 저장된 주제는 이랬다.

    '?? ??? ? ? ?? ????? ?? ??'

요청을 UTF-8로 보내지 않아 한글이 물음표가 됐다. Writer는 주제를
받지 못한 채 대본을 썼다. 주제가 온전한 29편을 다시 재 보니 제목
이탈은 1편(3%), 본문 이탈은 0편이었다.

그래서 여기서 막는 것은 두 가지다 - 알아볼 수 없는 주제로 Writer를
부르지 않는 것, 그리고 만들어진 대본이 주제를 담고 있는지 확인하는
것이다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import duration_gate, topic_fidelity
from app.services.topic_fidelity import TopicError


def _script(title, script="본문입니다.", narrations=("장면 하나",)):
    return {
        "title": title,
        "hook": "훅",
        "script": script,
        "scenes": [
            {"scene": i + 1, "narration": n}
            for i, n in enumerate(narrations)
        ],
    }


class TestAnUnreadableTopicStopsBeforeTheWriter(unittest.TestCase):
    """실제로 사고가 난 지점이다. 빈 주제를 받은 모델은 반드시
    무언가를 지어내고, 그 대본으로 이미지 6장과 음성과 영상이
    만들어진다."""

    def test_the_encoding_damaged_topic_from_pv02_is_rejected(self):
        with self.assertRaises(TopicError) as caught:
            topic_fidelity.validate_topic("?? ??? ? ? ?? ????? ?? ??")

        self.assertIn("UTF-8", str(caught.exception))

    def test_an_empty_topic_is_rejected(self):
        for bad in ("", "   ", None):
            with self.subTest(bad=bad):
                with self.assertRaises(TopicError):
                    topic_fidelity.validate_topic(bad)

    def test_a_topic_of_only_punctuation_is_rejected(self):
        for bad in ("???", "...", "!!! ???"):
            with self.subTest(bad=bad):
                with self.assertRaises(TopicError):
                    topic_fidelity.validate_topic(bad)

    def test_a_non_korean_topic_is_allowed(self):
        """실제로 사고를 낸 것은 영문이 아니라 글자가 사라진 문자열이다.
        한글을 강제하면 "vitamin D" 같은 멀쩡한 주제까지 막힌다."""

        self.assertEqual(topic_fidelity.validate_topic("vitamin D"), [])

    def test_a_real_topic_passes_and_returns_its_keywords(self):
        keywords = topic_fidelity.validate_topic("당뇨 예방에 좋은 아침 식사")

        self.assertIn("당뇨", keywords)
        self.assertIn("아침", keywords)

    def test_the_gate_never_calls_the_writer_for_a_bad_topic(self):
        """Gemini도 Imagen도 부르기 전에 멈춰야 한다."""

        writer = unittest.mock.Mock()

        with self.assertRaises(TopicError):
            duration_gate.generate_script_within_duration(
                topic="????", generate_fn=writer,
            )

        writer.assert_not_called()


class TestTopicKeywordsReadTheWholePhrase(unittest.TestCase):
    """korean_noun_filter(Sprint94)는 조사가 붙은 적이 있는지를 명사의
    증거로 요구한다. 긴 대본에는 맞지만 사람이 쓴 짧은 주제구에는
    맞지 않는다 - 실측에서 제목에 "당뇨"가 뻔히 있는데 이탈로 셌다."""

    def test_words_without_a_particle_are_still_keywords(self):
        keywords = topic_fidelity.topic_keywords("당뇨 예방에 좋은 아침 식사")

        for word in ("당뇨", "예방", "아침", "식사"):
            with self.subTest(word=word):
                self.assertIn(word, keywords)

    def test_particles_are_stripped(self):
        self.assertIn("치매", topic_fidelity.topic_keywords("치매를 늦추는 습관"))

    def test_a_word_whose_stem_is_one_character_is_dropped(self):
        """"물 한 잔이"의 "잔이"는 조사를 떼면 한 글자가 되는데, 어간
        최소 길이가 2라 조사가 안 떨어지고 "잔이"로 남는다. 그러면
        제목의 "물 한 잔"과 영영 안 맞는다 - 있으나 마나가 아니라
        없는 것만 못하다."""

        keywords = topic_fidelity.topic_keywords(
            "아침 공복에 물 한 잔이 혈액순환에 주는 변화",
        )

        self.assertNotIn("잔이", keywords)
        self.assertIn("공복", keywords)
        self.assertIn("혈액순환", keywords)

    def test_function_words_are_dropped(self):
        keywords = topic_fidelity.topic_keywords("그냥 정말 혈압 관리")

        self.assertNotIn("그냥", keywords)
        self.assertNotIn("정말", keywords)
        self.assertIn("혈압", keywords)


class TestTheCheckSeparatesTitleFromBody(unittest.TestCase):
    """본문은 주제를 다루면서 제목만 "이것"으로 가리는 경우가 실제로
    있었다(실측 1/29). 그 둘은 다른 문제다."""

    def test_a_faithful_script_passes(self):
        result = topic_fidelity.check(
            "치매를 늦추는 생활 습관",
            _script("절대 치매 안 걸리는 사람들의 '이것'",
                    "치매는 예방할 수 있습니다."),
        )

        self.assertTrue(result["passed"])
        self.assertIn("치매", result["in_title"])

    def test_a_title_that_hides_the_subject_fails(self):
        result = topic_fidelity.check(
            "저녁 취침 전 스트레칭이 수면에 미치는 영향",
            _script("매일 밤 뒤척인다면 '이것' 5분만 하세요",
                    "스트레칭이 도움이 됩니다."),
        )

        self.assertFalse(result["title_ok"])
        self.assertTrue(result["body_ok"])
        self.assertFalse(result["passed"])

    def test_the_coffee_case_would_have_been_caught(self):
        """주제가 온전했다면 이런 대본은 통과하지 못한다."""

        result = topic_fidelity.check(
            "아침 공복에 물 한 잔이 혈액순환에 주는 변화",
            _script("의사들이 절대 말해주지 않는 커피의 충격적인 진실",
                    "빈속에 커피를 마시면 위벽이 손상됩니다."),
        )

        self.assertFalse(result["passed"])

    def test_narration_counts_as_body(self):
        result = topic_fidelity.check(
            "혈압 관리",
            _script("건강해지는 '이것'", "", ("혈압을 낮추는 방법입니다",)),
        )

        self.assertTrue(result["body_ok"])


class TestTheGateAcceptsOnlyBothCriteria(unittest.TestCase):

    def _run(self, scripts, **kwargs):
        calls = {"n": 0}

        def writer(topic, target_duration, scene_count):
            data = scripts[min(calls["n"], len(scripts) - 1)]
            calls["n"] += 1
            return {"success": True, "data": data}

        outcome = duration_gate.generate_script_within_duration(
            topic="치매를 늦추는 생활 습관",
            generate_fn=writer,
            estimate_fn=lambda scenes: kwargs.get("seconds", 45.0),
        )
        return outcome, calls["n"]

    def test_a_faithful_script_of_the_right_length_passes_first_try(self):
        outcome, attempts = self._run([_script("치매 예방법", "치매 이야기")])

        self.assertTrue(outcome["passed"])
        self.assertEqual(attempts, 1)

    def test_a_drifted_script_is_regenerated(self):
        outcome, attempts = self._run([
            _script("완전히 다른 이야기", "전혀 다른 내용"),
            _script("치매를 막는 습관", "치매 이야기"),
        ])

        self.assertTrue(outcome["passed"])
        self.assertEqual(attempts, 2)

    def test_the_retry_budget_is_not_multiplied(self):
        """게이트를 하나 더 쌓으면 최악의 경우 호출이 3회에서 9회로
        늘어난다. 한 대본을 두 기준으로 함께 본다."""

        _, attempts = self._run([_script("다른 이야기", "다른 내용")])

        self.assertEqual(attempts, duration_gate.MAX_ATTEMPTS)

    def test_a_faithful_script_beats_a_merely_well_sized_one(self):
        """주제를 벗어난 영상은 길이가 정확해도 쓸 수 없다."""

        calls = {"n": 0}
        scripts = [
            _script("전혀 다른 소재", "다른 내용"),      # 길이는 완벽
            _script("치매 예방 습관", "치매 이야기"),     # 주제는 맞음
            _script("또 다른 소재", "다른 내용"),
        ]
        seconds = [45.0, 40.0, 45.0]

        def writer(topic, target_duration, scene_count):
            data = scripts[calls["n"]]
            calls["n"] += 1
            return {"success": True, "data": data}

        outcome = duration_gate.generate_script_within_duration(
            topic="치매를 늦추는 생활 습관",
            generate_fn=writer,
            estimate_fn=lambda scenes: seconds[calls["n"] - 1],
        )

        self.assertTrue(outcome["topic_fidelity"]["passed"])
        self.assertEqual(outcome["result"]["data"]["title"], "치매 예방 습관")

    def test_the_outcome_carries_the_fidelity_report(self):
        outcome, _ = self._run([_script("치매 예방법", "치매 이야기")])

        self.assertIn("topic_fidelity", outcome)
        self.assertIn("keywords", outcome["topic_fidelity"])


class TestThePromptCarriesTheRule(unittest.TestCase):

    def test_the_topic_lock_rule_is_in_the_prompt(self):
        from app.prompts.script_prompt import SCRIPT_PROMPT

        rendered = SCRIPT_PROMPT.substitute(
            topic="치매", target_duration=45, scene_count=6,
        )

        self.assertIn("주제 고정 규칙", rendered)
        self.assertIn("핵심 단어가 최소 하나 그대로 들어간다", rendered)

    def test_the_topic_is_still_injected(self):
        from app.prompts.script_prompt import SCRIPT_PROMPT

        rendered = SCRIPT_PROMPT.substitute(
            topic="고혈압 관리", target_duration=45, scene_count=6,
        )

        self.assertIn("고혈압 관리", rendered)


class TestNoAIIsCalled(unittest.TestCase):

    def test_the_module_imports_no_ai_provider(self):
        import ast

        tree = ast.parse(open(topic_fidelity.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)

        for forbidden in ("genai", "script_service", "ai_provider_manager"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(any(forbidden in n for n in names), forbidden)


class TestNothingOutsideScriptChanged(unittest.TestCase):
    """범위 - Script 생성만. Metadata/Upload/Image Prompt 변경 금지."""

    def test_the_image_prompt_rules_are_untouched(self):
        from app.prompts import image_prompt_rules

        source = open(image_prompt_rules.__file__, encoding="utf-8").read()

        self.assertNotIn("주제 고정", source)
        self.assertNotIn("Sprint95", source)

    def test_metadata_does_not_import_topic_fidelity(self):
        import ast

        from app.services import metadata_service

        tree = ast.parse(open(metadata_service.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.update(a.name for a in node.names)

        self.assertNotIn("topic_fidelity", names)


if __name__ == "__main__":
    unittest.main()
