import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.visual_type_classifier import (
    VISUAL_TYPE_AI,
    VISUAL_TYPE_REAL,
    apply_visual_type,
    determine_visual_type,
)


class TestDetermineVisualType(unittest.TestCase):

    def test_ai_keyword_in_korean_narration_returns_ai(self):
        scene = {
            "narration": "혈관 건강을 지키는 방법을 알아봅시다.",
            "image_prompt": "a healthy lifestyle scene",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_AI)

    def test_ai_keyword_in_english_image_prompt_returns_ai(self):
        scene = {
            "narration": "우리 몸은 놀랍습니다.",
            "image_prompt": "3D render of a human cell with mitochondria inside",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_AI)

    def test_real_keyword_returns_real(self):
        scene = {
            "narration": "병원에서 의사 선생님을 만났어요.",
            "image_prompt": "a doctor talking to a patient at a hospital",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_REAL)

    def test_no_keywords_defaults_to_real(self):
        scene = {
            "narration": "오늘은 좋은 날입니다.",
            "image_prompt": "a calm scene",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_REAL)

    def test_tie_score_defaults_to_real(self):
        # ai 키워드 1개("세포") vs real 키워드 1개("병원") - 동점이면 real.
        scene = {
            "narration": "세포",
            "image_prompt": "hospital",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_REAL)

    def test_ai_must_strictly_outscore_real(self):
        # ai 2개("세포", "염증") vs real 1개("병원") - ai가 확실히 많으면 ai.
        scene = {
            "narration": "세포와 염증 반응",
            "image_prompt": "hospital",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_AI)

    def test_missing_fields_do_not_raise(self):
        self.assertEqual(determine_visual_type({}), VISUAL_TYPE_REAL)

    def test_drinking_water_scene_is_real(self):
        scene = {
            "narration": "아침 공복에 물 한 잔 마시는 습관",
            "image_prompt": "a glass of water on a kitchen table in the morning",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_REAL)

    def test_gut_bacteria_scene_is_ai(self):
        scene = {
            "narration": "장내세균과 유익균의 균형이 중요합니다.",
            "image_prompt": "microscopic view of gut bacteria and probiotics",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_AI)

    def test_ascii_keyword_uses_word_boundary_not_substring(self):
        # "cell"이 "cellular"(세포와 무관하게 쓰이는 다른 단어) 안에서
        # 오탐되면 안 된다.
        scene = {
            "narration": "",
            "image_prompt": "a cellular phone on a wooden desk",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_REAL)

    def test_generic_woman_man_keywords_are_not_ai_or_real_signals(self):
        # Visual Consistency Engine이 모든 image_prompt에 넣는 "Korean
        # woman/man" 표현이 real_score를 밀어올려 ai 신호를 덮으면 안
        # 된다 - "woman"/"man"은 REAL_VISUAL_KEYWORDS에 없어야 한다.
        scene = {
            "narration": "혈관 건강",
            "image_prompt": "Close-up of a Korean woman looking at a blood vessel diagram",
        }
        self.assertEqual(determine_visual_type(scene), VISUAL_TYPE_AI)


class TestApplyVisualType(unittest.TestCase):

    def test_sets_visual_type_field_on_each_scene(self):
        scenes = [
            {"scene": 1, "narration": "혈관", "image_prompt": "p"},
            {"scene": 2, "narration": "병원", "image_prompt": "p"},
        ]

        result = apply_visual_type(scenes)

        self.assertEqual(result[0]["visual_type"], VISUAL_TYPE_AI)
        self.assertEqual(result[1]["visual_type"], VISUAL_TYPE_REAL)

    def test_value_is_always_real_or_ai(self):
        scenes = [{"scene": 1, "narration": "n", "image_prompt": "p"}]
        result = apply_visual_type(scenes)
        self.assertIn(result[0]["visual_type"], (VISUAL_TYPE_REAL, VISUAL_TYPE_AI))

    def test_does_not_mutate_input_scenes(self):
        scenes = [{"scene": 1, "narration": "혈관", "image_prompt": "p"}]
        original = [dict(s) for s in scenes]

        apply_visual_type(scenes)

        self.assertEqual(scenes, original)

    def test_returns_new_list_not_same_objects(self):
        scenes = [{"scene": 1, "narration": "n", "image_prompt": "p"}]
        result = apply_visual_type(scenes)
        self.assertIsNot(result[0], scenes[0])

    def test_preserves_other_scene_fields(self):
        scenes = [{"scene": 1, "narration": "n", "image_prompt": "p", "extra": "kept"}]
        result = apply_visual_type(scenes)
        self.assertEqual(result[0]["extra"], "kept")
        self.assertEqual(result[0]["scene"], 1)

    def test_empty_list_returns_empty_list(self):
        self.assertEqual(apply_visual_type([]), [])

    def test_none_returns_empty_list(self):
        self.assertEqual(apply_visual_type(None), [])

    def test_scene_order_preserved(self):
        scenes = [
            {"scene": 3, "narration": "n", "image_prompt": "p"},
            {"scene": 1, "narration": "n", "image_prompt": "p"},
        ]
        result = apply_visual_type(scenes)
        self.assertEqual([s["scene"] for s in result], [3, 1])


if __name__ == "__main__":
    unittest.main()
