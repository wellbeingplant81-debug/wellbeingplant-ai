import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.emphasis_engine import apply_emphasis


class TestEmphasisEngine(unittest.TestCase):

    def test_empty_text_returns_unchanged(self):
        self.assertEqual(apply_emphasis("", ["단순한"]), "")

    def test_empty_keywords_returns_unchanged(self):
        text = "단순한 노화가 아닐 수도 있습니다."
        self.assertEqual(apply_emphasis(text, []), text)
        self.assertEqual(apply_emphasis(text, None), text)

    def test_keyword_gets_pre_pause(self):
        text = "그 원인은 단순한 노화가 아닐 수도 있습니다."
        result = apply_emphasis(text, ["노화"])
        self.assertIn('<break time="0.15s" /> 노화', result)

    def test_multiple_occurrences_all_emphasized(self):
        text = "노화, 노화, 노화입니다."
        result = apply_emphasis(text, ["노화"])
        self.assertEqual(result.count('<break time="0.15s" /> 노화'), 3)

    def test_missing_keyword_no_change(self):
        text = "단순한 노화가 아닐 수도 있습니다."
        result = apply_emphasis(text, ["없는단어"])
        self.assertEqual(result, text)

    def test_original_text_not_mutated(self):
        original = "그 원인은 단순한 노화가 아닐 수도 있습니다."
        snapshot = original
        apply_emphasis(original, ["노화"])
        self.assertEqual(original, snapshot)

    def test_custom_pause_duration(self):
        text = "노화가 원인입니다."
        result = apply_emphasis(text, ["노화"], pre_pause=0.3)
        self.assertIn('<break time="0.3s" /> 노화', result)


if __name__ == "__main__":
    unittest.main()
