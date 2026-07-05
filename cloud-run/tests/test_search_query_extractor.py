import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.search_query_extractor import extract_search_query


class TestSearchQueryExtractor(unittest.TestCase):

    def test_empty_prompt_returns_empty(self):
        self.assertEqual(extract_search_query(""), "")

    def test_filler_phrases_removed(self):
        prompt = "Ultra realistic, cinematic photography, tired woman in office."
        result = extract_search_query(prompt)
        self.assertNotIn("ultra", result)
        self.assertNotIn("realistic", result)
        self.assertNotIn("cinematic", result)

    def test_core_subject_words_survive(self):
        prompt = "Ultra realistic, cinematic photography of a tired woman sitting at a messy office desk."
        result = extract_search_query(prompt)
        self.assertIn("tired", result)
        self.assertIn("woman", result)
        self.assertIn("office", result)

    def test_max_words_truncation(self):
        prompt = "one two three four five six seven eight nine ten"
        result = extract_search_query(prompt, max_words=3)
        self.assertEqual(result, "one two three")

    def test_punctuation_stripped(self):
        prompt = "Scene 1: Korean woman, shocked expression!"
        result = extract_search_query(prompt)
        self.assertNotIn(":", result)
        self.assertNotIn(",", result)
        self.assertNotIn("!", result)

    def test_original_prompt_not_mutated(self):
        prompt = "Ultra realistic photo of a tired woman."
        snapshot = prompt
        extract_search_query(prompt)
        self.assertEqual(prompt, snapshot)


if __name__ == "__main__":
    unittest.main()
