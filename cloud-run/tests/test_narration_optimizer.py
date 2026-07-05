import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.narration_optimizer import optimize_narration


class TestNarrationOptimizer(unittest.TestCase):

    def test_empty_text_returns_empty(self):
        self.assertEqual(optimize_narration(""), "")

    def test_short_sentence_unchanged(self):
        text = "오늘은 좋은 날입니다."
        self.assertEqual(optimize_narration(text), text)

    def test_long_sentence_with_comma_is_split(self):
        long_sentence = (
            "우리 몸은 나이가 들면서 자연스럽게 여러 변화를 겪게 되는데, "
            "그중 하나가 바로 방광 기능의 저하입니다."
        )
        result = optimize_narration(long_sentence, max_sentence_length=40)
        self.assertGreater(result.count("."), long_sentence.count("."))

    def test_long_sentence_without_comma_stays_one_piece(self):
        long_sentence = "가" * 50 + "다"
        result = optimize_narration(long_sentence, max_sentence_length=40)
        self.assertEqual(result.strip("."), long_sentence)

    def test_original_text_not_mutated(self):
        original = (
            "우리 몸은 나이가 들면서 자연스럽게 여러 변화를 겪게 되는데, "
            "그중 하나가 바로 방광 기능의 저하입니다."
        )
        snapshot = original
        optimize_narration(original)
        self.assertEqual(original, snapshot)

    def test_custom_max_length_threshold(self):
        text = "짧은 문장, 입니다."
        unchanged = optimize_narration(text, max_sentence_length=100)
        self.assertEqual(unchanged, text)


if __name__ == "__main__":
    unittest.main()
