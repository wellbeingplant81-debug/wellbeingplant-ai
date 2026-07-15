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


class TestCameraMetaWordsStripped(unittest.TestCase):
    """
    Sprint103 - Semantic Query Intelligence. image_prompt_rules.py가
    강제하는 카메라 앵글 선행 문장 구조(예: "High angle, camera
    positioned above the subject looking downward")에서 나온 촬영
    메타 어휘를 stripper의 책임 범위로 확장한다. 이 어휘들은 스톡
    영상/이미지 검색에 아무 가치가 없는데도 Sprint102 실측에서 8단어
    예산의 절반 가까이를 차지해 실제 피사체/행동 명사를 밀어냈다.
    """

    def test_camera_angle_words_removed(self):
        result = strip_style_boilerplate(
            "high angle shot dimly lit hospital room capturing a somber mood"
        )
        for leftover in ["high", "angle", "shot", "capturing"]:
            self.assertNotIn(leftover, result.split())
        for kept in ["dimly", "lit", "hospital", "room", "somber"]:
            self.assertIn(kept, result)

    def test_shot_type_words_removed(self):
        result = strip_style_boilerplate(
            "wide shot showing a fit korean man walking briskly"
        )
        for leftover in ["wide", "shot", "showing"]:
            self.assertNotIn(leftover, result.split())
        for kept in ["fit", "korean", "man", "walking", "briskly"]:
            self.assertIn(kept, result)

        result = strip_style_boilerplate(
            "medium shot showing a woman stretching on a yoga mat"
        )
        self.assertNotIn("medium", result.split())
        self.assertIn("stretching", result)
        self.assertIn("mat", result)

    def test_close_up_and_framing_words_removed(self):
        result = strip_style_boilerplate(
            "close up framing tightly on a family gathered around a table"
        )
        for leftover in ["close", "up", "framing"]:
            self.assertNotIn(leftover, result.split())
        for kept in ["tightly", "family", "gathered", "table"]:
            self.assertIn(kept, result)

    def test_derived_camera_positioning_words_removed(self):
        # image_prompt_rules.py L78/82/84가 나열한 "over-the-shoulder",
        # "top-down view", "eye-level shot"에서 나온 파생어들.
        result = strip_style_boilerplate(
            "over the shoulder shot of a doctor, top down view of "
            "a plate, eye level shot of a patient"
        )
        for leftover in ["over", "shoulder", "top", "down", "eye", "level", "shot"]:
            self.assertNotIn(leftover, result.split())
        for kept in ["doctor", "plate", "patient"]:
            self.assertIn(kept, result)

    def test_mood_and_dramatic_words_removed(self):
        result = strip_style_boilerplate(
            "an artery narrowing due to plaque buildup, dramatic lighting, somber mood"
        )
        for leftover in ["dramatic", "lighting", "mood"]:
            self.assertNotIn(leftover, result.split())
        for kept in ["artery", "narrowing", "plaque", "buildup", "somber"]:
            self.assertIn(kept, result)

    def test_word_boundary_does_not_strip_substrings_of_camera_words(self):
        # "shot"을 지우되 "shotgun" 같은 무관한 단어는 건드리지 않는다
        # (실제 도메인엔 안 나오는 예시지만 단어 경계 원칙을 고정한다).
        result = strip_style_boilerplate("a shotgun shell on a wooden shelf")
        self.assertIn("shotgun", result)
        self.assertIn("shelf", result)


if __name__ == "__main__":
    unittest.main()
