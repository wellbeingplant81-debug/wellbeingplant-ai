"""
Sprint71 - Character Consistency Engine v1.

Evaluation Framework v2로 5회 측정했더니 character_consistency가 5회
전부 0점이었다. 원인을 대본에서 찾았다.

  scene 1: middle-aged Korean man
  scene 3: Korean woman in her 50s
  scene 5: elderly Korean couple

Writer가 장면마다 다른 사람을 쓰고 있었다. 이미지 계층에서 "같은
인물"이라고 덧붙여 봐야 대본이 요구하는 인물과 정면으로 어긋날 뿐이다 -
Scene Planner v1이 "close-up shot"에 "wide shot"을 덧붙여 망가뜨렸던
것과 똑같은 실수가 된다.

그래서 일관성은 인물이 정해지는 곳, 즉 Writer에서 확립한다. 이미지
계층이 하는 일은 그 결정이 렌더까지 살아남게 하는 것뿐이다 - 인물이
나오는 scene을 Imagen으로 보낸다. Pexels 스톡은 매번 다른 실제 사람을
돌려주므로 대본이 아무리 같은 인물을 지정해도 지킬 수가 없다.

엔진은 image_prompt 텍스트를 절대 건드리지 않는다. 그것이 이 설계의
핵심이다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.prompts import character_consistency_rules
from app.services import character_consistency_engine as engine
from app.services.visual_type_classifier import VISUAL_TYPE_AI, VISUAL_TYPE_REAL


# 실제 산출물(output/20260709_165931)의 프롬프트.
REAL_SCENES = [
    {"scene": 1, "narration": "혹시 혈관에 기름때가 끼는 상상 해보셨나요?",
     "image_prompt": "Eye-level close-up of a middle-aged Korean man with a "
                     "shocked expression, pointing at a tablet",
     "visual_type": VISUAL_TYPE_REAL},
    {"scene": 2, "narration": "나쁜 콜레스테롤은 혈관 벽에 쌓입니다.",
     "image_prompt": "A macro top-down view inside a realistic human artery "
                     "with yellowish plaque",
     "visual_type": VISUAL_TYPE_AI},
    {"scene": 3, "narration": "매일 아침 걷기만 하면 됩니다.",
     "image_prompt": "Low-angle wide shot of a serene Korean woman in her 50s "
                     "starting her walk in a lush park",
     "visual_type": VISUAL_TYPE_REAL},
    {"scene": 4, "narration": "혈액순환이 좋아집니다.",
     "image_prompt": "Dynamic low-angle close-up shot of running shoes "
                     "hitting an asphalt path",
     "visual_type": VISUAL_TYPE_AI},
    {"scene": 5, "narration": "활기찬 노년을 보낼 수 있습니다.",
     "image_prompt": "Eye-level medium shot of a healthy elderly Korean "
                     "couple laughing warmly",
     "visual_type": VISUAL_TYPE_REAL},
    {"scene": 6, "narration": "오늘부터 30분, 시작해보세요!",
     "image_prompt": "Over-the-shoulder shot focusing on a person's hand "
                     "setting a timer on a smartwatch",
     "visual_type": VISUAL_TYPE_REAL},
]


class TestFlagState(unittest.TestCase):

    def test_flag_exists_and_is_off_until_the_ab_says_otherwise(self):
        self.assertFalse(config.ENABLE_CHARACTER_CONSISTENCY)

    def test_engines_pending_their_own_evaluation_stay_disabled(self):
        self.assertFalse(config.ENABLE_SCENE_PLANNER)
        self.assertFalse(config.ENABLE_PROMPT_ENRICHMENT)
        self.assertFalse(config.ENABLE_PROMPT_OPTIMIZATION)


class TestPersonDetection(unittest.TestCase):

    def test_scenes_with_a_person_are_detected(self):
        for prompt in (
            "Eye-level close-up of a middle-aged Korean man",
            "a serene Korean woman in her 50s starting her walk",
            "a healthy elderly Korean couple laughing",
            "Over-the-shoulder shot focusing on a person's hand",
            "웃고 있는 중년 남성의 모습",
        ):
            with self.subTest(prompt=prompt):
                self.assertTrue(
                    engine.features_person({"image_prompt": prompt}),
                )

    def test_scenes_without_a_person_are_not_detected(self):
        for prompt in (
            "A macro top-down view inside a realistic human artery",
            "Dynamic low-angle close-up shot of running shoes on asphalt",
            "A bowl of fresh blueberries on a wooden table",
            "",
        ):
            with self.subTest(prompt=prompt):
                self.assertFalse(
                    engine.features_person({"image_prompt": prompt}),
                )

    def test_human_artery_is_not_a_person(self):
        # "human"이라는 단어만 보고 인물로 판정하면 혈관/세포 장면이
        # 전부 Imagen 인물 경로로 새어 들어간다.
        self.assertFalse(
            engine.features_person({
                "image_prompt": "macro view inside a human artery",
            })
        )

    def test_detection_reads_the_prompt_not_the_narration(self):
        # 나레이션에는 사람 이야기가 나와도 화면에 사람이 없을 수
        # 있다. 라우팅을 정하는 근거는 화면이다.
        scene = {
            "narration": "많은 사람들이 이 습관을 놓칩니다.",
            "image_prompt": "A bowl of fresh blueberries on a wooden table",
        }

        self.assertFalse(engine.features_person(scene))


class TestRouting(unittest.TestCase):

    def test_person_scenes_are_routed_to_imagen(self):
        routed = engine.apply_character_routing(REAL_SCENES)
        by_scene = {scene["scene"]: scene for scene in routed}

        for number in (1, 3, 5, 6):
            self.assertEqual(
                by_scene[number]["visual_type"], VISUAL_TYPE_AI,
                f"scene {number}는 인물이 나오므로 Imagen으로 가야 한다",
            )

    def test_scenes_without_a_person_keep_their_routing(self):
        routed = engine.apply_character_routing(REAL_SCENES)
        by_scene = {scene["scene"]: scene for scene in routed}

        for number in (2, 4):
            original = next(s for s in REAL_SCENES if s["scene"] == number)
            self.assertEqual(
                by_scene[number]["visual_type"], original["visual_type"],
            )

    def test_image_prompts_are_never_touched(self):
        # 이 엔진의 핵심 계약. 프롬프트에 "같은 인물"을 덧붙이면 대본이
        # 지정한 인물과 모순된다 - Scene Planner v1이 낸 사고와 같다.
        routed = engine.apply_character_routing(REAL_SCENES)

        for original, result in zip(REAL_SCENES, routed):
            self.assertEqual(
                result["image_prompt"], original["image_prompt"],
            )

    def test_narration_and_order_are_untouched(self):
        routed = engine.apply_character_routing(REAL_SCENES)

        self.assertEqual(
            [s["scene"] for s in routed], [s["scene"] for s in REAL_SCENES],
        )
        for original, result in zip(REAL_SCENES, routed):
            self.assertEqual(result["narration"], original["narration"])

    def test_input_scenes_are_not_mutated(self):
        snapshot = [dict(scene) for scene in REAL_SCENES]

        engine.apply_character_routing(REAL_SCENES)

        self.assertEqual(REAL_SCENES, snapshot)

    def test_empty_input_is_handled(self):
        self.assertEqual(engine.apply_character_routing([]), [])
        self.assertEqual(engine.apply_character_routing(None), [])

    def test_routed_scene_numbers_are_reported(self):
        numbers = engine.character_scene_numbers(REAL_SCENES)
        self.assertEqual(numbers, [1, 3, 5, 6])


class TestWriterInstruction(unittest.TestCase):

    def test_the_instruction_asks_for_one_recurring_character(self):
        text = character_consistency_rules.CHARACTER_CONSISTENCY_RULES

        self.assertTrue(text.strip())
        self.assertIn("동일", text)

    def test_the_instruction_composes_onto_any_template(self):
        base = "원래 템플릿 본문"

        combined = character_consistency_rules.with_character_rules(base)

        self.assertTrue(combined.startswith(base))
        self.assertIn(
            character_consistency_rules.CHARACTER_CONSISTENCY_RULES.strip(),
            combined,
        )

    def test_script_service_adds_the_instruction_only_when_enabled(self):
        from app.services import script_service

        captured = {}

        class _Response:
            # script_service가 scene 하나를 꺼내 키를 찍어 보므로,
            # 빈 배열이 아니라 실제 형태를 돌려줘야 한다.
            text = (
                '{"title":"t","hook":"h","script":"s","scenes":'
                '[{"scene":1,"narration":"n","image_prompt":"p"}]}'
            )

        def fake_generate(model, contents):
            captured["prompt"] = contents
            return _Response()

        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                captured.clear()

                with patch.object(
                    config, "ENABLE_CHARACTER_CONSISTENCY", enabled,
                ), patch.object(
                    script_service.client.models, "generate_content",
                    fake_generate,
                ):
                    script_service.generate_script("주제")

                marker = (
                    character_consistency_rules
                    .CHARACTER_CONSISTENCY_RULES.strip()
                )

                if enabled:
                    self.assertIn(marker, captured["prompt"])
                else:
                    self.assertNotIn(marker, captured["prompt"])


if __name__ == "__main__":
    unittest.main()
