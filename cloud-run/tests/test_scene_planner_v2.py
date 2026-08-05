"""
Sprint69 - Scene Planner v2.

Stage 3 A/B에서 드러난 결함: Planner가 카메라를 scene 위치만으로 정하고
(첫 scene=close_up, 마지막=medium_shot, 나머지=wide_shot) 프롬프트가
이미 지시한 카메라를 읽지 않았다. 실측 6개 중 3개가 충돌했고, "dynamic
low-angle close-up shot"에 "wide shot"이 덧붙은 scene 4는 결과 이미지에
뜻 없는 가짜 라벨이 박혔다.

v2의 원칙은 하나다 - 프롬프트가 이미 말하고 있는 것은 건드리지 않는다.
프롬프트가 카메라를 지시하면 Planner는 그것을 채택하고, Enrichment는
그 차원의 문구를 덧붙이지 않는다. 프롬프트가 침묵할 때만 보완한다.

그래서 충돌은 "감지해서 고치는" 것이 아니라 애초에 생기지 않는다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import prompt_enrichment_service, scene_planner_service
from app.services.search_query_extractor import extract_search_query


# 실제 산출물(output/20260709_165931)에서 가져온 프롬프트들.
REAL_PROMPTS = {
    1: "Eye-level close-up of a middle-aged Korean man with a shocked "
       "expression, pointing at a tablet displaying a clogged artery",
    2: "Macro top-down view inside a realistic human artery, thick yellow "
       "plaque narrowing the passage, dramatic side lighting",
    3: "Low angle wide shot of a serene Korean woman in her 50s walking "
       "along a sunlit riverside path in the early morning",
    4: "Dynamic low-angle close-up shot of running shoes hitting the "
       "asphalt, glowing veins visible along the calf",
    5: "Eye-level medium shot of a healthy vibrant elderly Korean couple "
       "laughing together in a bright kitchen",
    6: "Over-the-shoulder shot focusing on a person's hand setting a phone "
       "timer on a wooden table",
}


class TestDetectCamera(unittest.TestCase):

    def test_close_up_is_detected(self):
        for prompt in (
            "Eye-level close-up of a man",
            "a close up of a hand",
            "dramatic closeup on the eyes",
            "Extreme close-up of a water droplet",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    scene_planner_service.detect_camera(prompt),
                    scene_planner_service.HOOK_CAMERA,
                )

    def test_macro_counts_as_close_up(self):
        # "macro"는 표현만 다를 뿐 극단적인 클로즈업이다. 여기에
        # "wide shot"을 덧붙이면 정확히 Stage 3가 낸 사고가 난다.
        self.assertEqual(
            scene_planner_service.detect_camera(
                "Macro top-down view inside a human artery"
            ),
            scene_planner_service.HOOK_CAMERA,
        )

    def test_medium_shot_is_detected(self):
        for prompt in (
            "Eye-level medium shot of a couple",
            "a medium-shot of two people talking",
            "waist-up portrait of a woman",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    scene_planner_service.detect_camera(prompt),
                    scene_planner_service.CTA_CAMERA,
                )

    def test_wide_shot_is_detected(self):
        for prompt in (
            "Low angle wide shot of a riverside path",
            "a wide-angle view of the city",
            "establishing shot of a hospital",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    scene_planner_service.detect_camera(prompt),
                    scene_planner_service.DEVELOPMENT_CAMERA,
                )

    def test_a_prompt_without_a_camera_returns_none(self):
        for prompt in (
            "Over-the-shoulder shot focusing on a person's hand",
            "A serene morning by the river",
            "",
            None,
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(scene_planner_service.detect_camera(prompt))

    def test_the_first_stated_framing_wins(self):
        # 두 개가 섞여 있으면 먼저 나온 것이 주 프레이밍이다.
        self.assertEqual(
            scene_planner_service.detect_camera(
                "Wide shot of a kitchen, with a close-up of the kettle"
            ),
            scene_planner_service.DEVELOPMENT_CAMERA,
        )
        self.assertEqual(
            scene_planner_service.detect_camera(
                "Close-up of a kettle in a wide bright kitchen scene"
            ),
            scene_planner_service.HOOK_CAMERA,
        )

    def test_detection_is_a_pure_function(self):
        prompt = "Eye-level close-up of a man"
        scene_planner_service.detect_camera(prompt)
        self.assertEqual(prompt, "Eye-level close-up of a man")


class TestPlannerRespectsTheProImpt(unittest.TestCase):

    def _plan(self, prompts):
        scenes = [
            {"scene": number, "narration": "n", "image_prompt": prompt}
            for number, prompt in sorted(prompts.items())
        ]
        return scene_planner_service.plan_scenes({"scenes": scenes})

    def test_camera_comes_from_the_prompt_when_it_says_one(self):
        plan = self._plan(REAL_PROMPTS)
        by_scene = {item["scene_id"]: item for item in plan}

        expected = {
            1: scene_planner_service.HOOK_CAMERA,        # close-up
            2: scene_planner_service.HOOK_CAMERA,        # macro
            3: scene_planner_service.DEVELOPMENT_CAMERA,  # wide shot
            4: scene_planner_service.HOOK_CAMERA,        # close-up
            5: scene_planner_service.CTA_CAMERA,         # medium shot
        }

        for scene_id, camera in expected.items():
            self.assertEqual(by_scene[scene_id]["camera"], camera)
            self.assertEqual(by_scene[scene_id]["camera_source"], "prompt")

    def test_position_still_decides_when_the_prompt_is_silent(self):
        plan = self._plan(REAL_PROMPTS)
        by_scene = {item["scene_id"]: item for item in plan}

        # scene 6 - "over-the-shoulder"는 프레이밍 크기를 말하지 않는다.
        # 마지막 scene이므로 기존 규칙대로 cta/medium_shot.
        self.assertEqual(
            by_scene[6]["camera"], scene_planner_service.CTA_CAMERA,
        )
        self.assertEqual(by_scene[6]["camera_source"], "planned")

    def test_purpose_is_still_decided_by_position(self):
        # v2는 카메라만 손댄다. 서사 역할은 위치가 정하는 것이 맞다.
        plan = self._plan(REAL_PROMPTS)

        self.assertEqual(plan[0]["purpose"], scene_planner_service.HOOK_PURPOSE)
        self.assertEqual(plan[-1]["purpose"], scene_planner_service.CTA_PURPOSE)

    def test_visual_type_source_is_recorded_too(self):
        plan = self._plan(REAL_PROMPTS)

        for item in plan:
            self.assertIn(item["visual_type_source"], ("prompt", "planned"))


class TestEnrichmentNeverContradictsThePrompt(unittest.TestCase):

    def _enriched(self, prompts):
        scenes = [
            {"scene": number, "narration": "n", "image_prompt": prompt}
            for number, prompt in sorted(prompts.items())
        ]
        plan = scene_planner_service.plan_scenes({"scenes": scenes})
        return scenes, plan, prompt_enrichment_service.apply_prompt_enrichment(
            scenes, plan,
        )

    def test_no_camera_phrase_is_added_when_the_prompt_has_one(self):
        scenes, plan, enriched = self._enriched(REAL_PROMPTS)
        by_scene = {item["scene_id"]: item for item in plan}

        for original, result in zip(scenes, enriched):
            if by_scene[original["scene"]]["camera_source"] != "prompt":
                continue

            added = result["image_prompt"][len(original["image_prompt"]):]

            for phrase in prompt_enrichment_service.CAMERA_PHRASES.values():
                self.assertNotIn(
                    phrase, added,
                    f"scene {original['scene']}: 프롬프트가 이미 카메라를 "
                    f"지시하는데 '{phrase}'를 덧붙였다",
                )

    def test_the_stage3_failure_case_no_longer_contradicts(self):
        # scene 4가 Stage 3에서 망가진 그 케이스.
        prompt = REAL_PROMPTS[4]

        scenes, plan, enriched = self._enriched(REAL_PROMPTS)
        result = next(s for s in enriched if s["scene"] == 4)

        self.assertIn("close-up", result["image_prompt"])
        self.assertNotIn("wide shot", result["image_prompt"])
        self.assertTrue(result["image_prompt"].startswith(prompt))

    def test_a_silent_prompt_still_gets_a_camera_phrase(self):
        scenes, plan, enriched = self._enriched(REAL_PROMPTS)

        result = next(s for s in enriched if s["scene"] == 6)
        added = result["image_prompt"][len(REAL_PROMPTS[6]):]

        self.assertIn(
            prompt_enrichment_service.CAMERA_PHRASES[
                scene_planner_service.CTA_CAMERA
            ],
            added,
        )

    def test_no_visual_type_phrase_is_added_when_the_prompt_has_one(self):
        prompts = {
            1: "A photorealistic portrait of a doctor in a bright clinic",
            2: "A medical illustration of a human heart with labelled valves",
        }

        scenes, plan, enriched = self._enriched(prompts)
        by_scene = {item["scene_id"]: item for item in plan}

        for original, result in zip(scenes, enriched):
            if by_scene[original["scene"]]["visual_type_source"] != "prompt":
                continue

            added = result["image_prompt"][len(original["image_prompt"]):]

            for phrase in prompt_enrichment_service.VISUAL_TYPE_PHRASES.values():
                self.assertNotIn(phrase, added)


class TestInvariantsStillHold(unittest.TestCase):
    """v1에서 지키던 계약은 v2에서도 그대로여야 한다."""

    def _enriched(self):
        scenes = [
            {"scene": number, "narration": f"나레이션 {number}",
             "image_prompt": prompt}
            for number, prompt in sorted(REAL_PROMPTS.items())
        ]
        plan = scene_planner_service.plan_scenes({"scenes": scenes})
        return scenes, prompt_enrichment_service.apply_prompt_enrichment(
            scenes, plan,
        )

    def test_enrichment_is_still_append_only(self):
        scenes, enriched = self._enriched()

        for original, result in zip(scenes, enriched):
            self.assertTrue(
                result["image_prompt"].startswith(original["image_prompt"])
            )

    def test_narration_is_untouched(self):
        scenes, enriched = self._enriched()

        for original, result in zip(scenes, enriched):
            self.assertEqual(result["narration"], original["narration"])

    def test_scene_order_is_untouched(self):
        scenes, enriched = self._enriched()

        self.assertEqual(
            [s["scene"] for s in enriched], [s["scene"] for s in scenes],
        )

    def test_stock_search_query_is_unchanged(self):
        scenes, enriched = self._enriched()

        for original, result in zip(scenes, enriched):
            self.assertEqual(
                extract_search_query(original["image_prompt"]),
                extract_search_query(result["image_prompt"]),
            )

    def test_planner_does_not_mutate_the_input(self):
        scenes = [
            {"scene": 1, "narration": "n", "image_prompt": REAL_PROMPTS[1]},
        ]
        snapshot = dict(scenes[0])

        scene_planner_service.plan_scenes({"scenes": scenes})

        self.assertEqual(scenes[0], snapshot)


if __name__ == "__main__":
    unittest.main()
