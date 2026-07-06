import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_priority_classifier import (
    classify_scene_importance,
    effective_pexels_threshold,
    select_ai_priority_scenes,
)


class TestClassifySceneImportance(unittest.TestCase):

    def test_medical_scene_prefers_ai(self):
        scene = {
            "narration": "우리 몸의 혈관과 세포는",
            "image_prompt": "diagram of blood vessel anatomy inside human organ",
        }

        result = classify_scene_importance(scene)

        self.assertTrue(result["prefers_ai"])
        self.assertGreater(result["ai_score"], result["pexels_score"])

    def test_lifestyle_scene_prefers_pexels(self):
        scene = {
            "narration": "아침 산책과 신선한 과일 한 조각",
            "image_prompt": "wide shot of a forest landscape with morning light",
        }

        result = classify_scene_importance(scene)

        self.assertFalse(result["prefers_ai"])

    def test_no_keywords_defaults_to_pexels(self):
        scene = {"narration": "", "image_prompt": ""}

        result = classify_scene_importance(scene)

        self.assertEqual(result["ai_score"], 0)
        self.assertEqual(result["pexels_score"], 0)
        self.assertFalse(result["prefers_ai"])

    def test_tie_defaults_to_pexels_not_ai(self):
        scene = {
            "narration": "사람이 숲에서",  # "사람"(AI) vs "숲"(Pexels): 1:1
            "image_prompt": "",
        }

        result = classify_scene_importance(scene)

        self.assertEqual(result["ai_score"], result["pexels_score"])
        self.assertFalse(result["prefers_ai"])

    def test_missing_fields_do_not_raise(self):
        result = classify_scene_importance({})

        self.assertFalse(result["prefers_ai"])

    def test_man_keyword_no_longer_falsely_matches_human_or_woman(self):
        # "man"/"woman"/"person"/"people"는 이 파이프라인의 모든 scene
        # image_prompt에 항상 등장해서(Sprint34 인물 일관성 스타일)
        # 의료/비의료를 구분하는 신호가 못 되므로 제거했다. "human"이나
        # "woman"이라는 단어 안에서 "man"이 부분 문자열로 잘못 잡히는
        # 문제도 이제 없어야 한다.
        scene = {
            "narration": "",
            "image_prompt": "a young korean woman standing near a human figure",
        }

        result = classify_scene_importance(scene)

        self.assertEqual(result["ai_score"], 0)

    def test_expanded_medical_keywords_are_detected(self):
        for word in [
            "stomach", "liver", "kidney", "heart", "brain", "lung",
            "intestine", "colon", "pancreas", "artery", "vein", "muscle",
            "bone", "skeleton", "digestive", "digestion", "xray", "mri",
            "ultrasound", "endoscopy", "microscope", "laboratory",
            "physician", "clinical",
        ]:
            with self.subTest(word=word):
                scene = {"narration": "", "image_prompt": f"a diagram of the {word}"}
                result = classify_scene_importance(scene)
                self.assertGreater(result["ai_score"], 0)


class TestEffectivePexelsThreshold(unittest.TestCase):

    def test_non_medical_scene_uses_base_threshold_unchanged(self):
        scene = {"narration": "숲과 바다", "image_prompt": "forest sea"}

        self.assertEqual(effective_pexels_threshold(scene, 0.90), 0.90)

    def test_strongly_medical_scene_raises_the_bar_above_base(self):
        scene = {
            "narration": "",
            "image_prompt": "diagram of stomach digestion anatomy organ",
        }

        threshold = effective_pexels_threshold(scene, 0.90)

        self.assertGreater(threshold, 0.90)

    def test_threshold_never_exceeds_the_configured_maximum(self):
        scene = {
            "narration": "",
            "image_prompt": (
                "stomach liver kidney heart brain lung intestine colon "
                "pancreas artery vein muscle bone skeleton digestive "
                "digestion anatomy organ cell vessel"
            ),
        }

        threshold = effective_pexels_threshold(scene, 0.90)

        self.assertLessEqual(threshold, 0.99)


class TestSelectAiPriorityScenes(unittest.TestCase):

    def test_empty_scenes_returns_empty_set(self):
        self.assertEqual(select_ai_priority_scenes([], ai_ratio_cap=0.3), set())

    def test_zero_cap_selects_nothing(self):
        scenes = [
            {"scene": 1, "narration": "혈관 질병", "image_prompt": "anatomy diagram"},
        ]

        self.assertEqual(select_ai_priority_scenes(scenes, ai_ratio_cap=0.0), set())

    def test_cap_limits_selection_to_highest_scoring_scenes(self):
        scenes = [
            {"scene": 1, "narration": "사람 의사", "image_prompt": "doctor person"},
            {
                "scene": 2,
                "narration": "혈관 세포 질병 해부학",
                "image_prompt": "organ anatomy medical diagram cell",
            },
            {"scene": 3, "narration": "병원", "image_prompt": "hospital"},
        ]

        # cap 1/3 -> round(3*0.34) = 1개만 선택되어야 하고, ai_score가
        # 가장 높은 scene 2가 선택되어야 한다.
        selected = select_ai_priority_scenes(scenes, ai_ratio_cap=0.34)

        self.assertEqual(selected, {2})

    def test_fewer_ai_priority_scenes_than_cap_does_not_force_fill(self):
        scenes = [
            {"scene": 1, "narration": "혈관", "image_prompt": "blood vessel"},
            {"scene": 2, "narration": "숲과 바다", "image_prompt": "forest sea"},
            {"scene": 3, "narration": "과일과 채소", "image_prompt": "fruit vegetable"},
        ]

        # cap이 아무리 커도(1.0=100%), 실제로 AI 우선인 scene은 1개뿐이니
        # 나머지 Pexels 우선 scene까지 억지로 채우면 안 된다.
        selected = select_ai_priority_scenes(scenes, ai_ratio_cap=1.0)

        self.assertEqual(selected, {1})

    def test_non_ai_priority_scenes_never_selected_regardless_of_cap(self):
        scenes = [
            {"scene": 1, "narration": "숲", "image_prompt": "forest"},
            {"scene": 2, "narration": "바다", "image_prompt": "sea"},
        ]

        selected = select_ai_priority_scenes(scenes, ai_ratio_cap=1.0)

        self.assertEqual(selected, set())


if __name__ == "__main__":
    unittest.main()
