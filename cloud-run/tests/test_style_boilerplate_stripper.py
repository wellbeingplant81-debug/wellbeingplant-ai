"""
Sprint102-2 - Style Boilerplate Strip. strip_style_boilerplate()가
image_prompt에서 스타일/화질/조명 상투어만 제거하고 장면의 실제 의미
(피사체/행동/배경)는 그대로 남기는지 확인한다.

순수 함수(네트워크/Gemini 호출 없음) - 결정적, mock 없이 유닛테스트
가능.

핵심 회귀 케이스: 2026-07-14 Production QA에서 실측된 문제 - 모든
image_prompt 끝에 붙는 공통 접미사("warm, soft, clean wellness
aesthetic, natural morning lighting, minimal composition, cinematic
feel.")의 "morning"/"wellness"가 video_search_planner.py의 lifestyle
카테고리와 매번 우연히 매칭되던 것을 재현하고, 이 계층을 거치면 더
이상 매칭되지 않아야 한다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.style_boilerplate_stripper import strip_style_boilerplate


class TestStripStyleBoilerplate(unittest.TestCase):

    def test_removes_real_production_suffix_entirely(self):
        # 2026-07-14 Production QA에서 실측된 실제 접미사 그대로.
        result = strip_style_boilerplate(
            "warm, soft, clean wellness aesthetic, natural morning "
            "lighting, minimal composition, cinematic feel."
        )
        for leftover in ["morning", "wellness", "warm", "soft", "clean", "cinematic"]:
            self.assertNotIn(leftover, result)

    def test_preserves_semantic_content_around_the_suffix(self):
        result = strip_style_boilerplate(
            "A Korean woman in her 40s holding a glass of vibrant orange "
            "juice in a modern kitchen. warm, soft, clean wellness "
            "aesthetic, natural morning lighting, minimal composition, "
            "cinematic feel."
        )
        for kept in ["korean", "woman", "orange", "juice", "kitchen"]:
            self.assertIn(kept, result)

    def test_examples_from_spec_are_all_stripped(self):
        prompt = (
            "a person walking in a park. warm soft clean wellness "
            "aesthetic natural lighting morning lighting cinematic "
            "lighting golden hour high quality ultra detailed"
        )
        result = strip_style_boilerplate(prompt)
        for phrase in [
            "warm", "soft", "clean", "wellness aesthetic", "natural lighting",
            "morning lighting", "cinematic lighting", "golden hour",
            "high quality", "ultra detailed",
        ]:
            self.assertNotIn(phrase, result)
        self.assertIn("walking", result)
        self.assertIn("park", result)

    def test_empty_input_returns_empty_string(self):
        self.assertEqual(strip_style_boilerplate(""), "")
        self.assertEqual(strip_style_boilerplate(None), "")

    def test_prompt_with_no_style_words_is_mostly_unchanged(self):
        result = strip_style_boilerplate("a doctor examines a patient in a clinic")
        for kept in ["doctor", "examines", "patient", "clinic"]:
            self.assertIn(kept, result)

    def test_does_not_mutate_input(self):
        original = "warm and soft lighting, a person walking"
        strip_style_boilerplate(original)
        self.assertEqual(
            original, "warm and soft lighting, a person walking",
        )

    def test_word_boundary_does_not_strip_substrings_of_semantic_words(self):
        # "warm"을 제거하되 "warmth"/"warming" 같은 다른 단어는
        # 건드리지 않는다(단어 경계 유지).
        result = strip_style_boilerplate("a warming sense of warmth in the room")
        self.assertIn("warming", result)
        self.assertIn("warmth", result)


if __name__ == "__main__":
    unittest.main()
