import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.smart_pause_engine import apply_smart_pause


class TestSmartPauseEngine(unittest.TestCase):

    def test_empty_text_returns_empty(self):
        self.assertEqual(apply_smart_pause(""), "")

    def test_sentence_boundary_gets_break_tag(self):
        result = apply_smart_pause("오늘은 좋은 날입니다. 내일도 그럴까요?")
        self.assertIn('<break time="0.4s" />', result)

    def test_comma_gets_shorter_break_tag(self):
        result = apply_smart_pause("첫째, 둘째, 셋째입니다.")
        self.assertIn('<break time="0.15s" />', result)

    def test_custom_durations_are_used(self):
        result = apply_smart_pause(
            "안녕하세요. 반갑습니다.",
            sentence_pause=1.0,
            comma_pause=0.5,
        )
        self.assertIn('<break time="1.0s" />', result)

    def test_original_text_not_mutated(self):
        original = "밤마다 화장실 때문에 자주 깨시나요?"
        snapshot = original
        apply_smart_pause(original)
        self.assertEqual(original, snapshot)

    def test_output_contains_original_words(self):
        original = "밤마다 화장실 때문에 자주 깨시나요?"
        result = apply_smart_pause(original)
        for word in ["밤마다", "화장실", "자주", "깨시나요"]:
            self.assertIn(word, result)


if __name__ == "__main__":
    unittest.main()
