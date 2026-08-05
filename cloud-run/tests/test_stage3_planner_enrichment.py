"""
Sprint68 (Stage 3) - Scene Planner + Prompt Enrichment.

Stage 1과 Stage 2의 엔진들은 켜도 산출물이 바이트 하나 달라지지 않았다.
여기서부터는 다르다 - Enrichment는 image_prompt를 실제로 바꾸고, 그
프롬프트로 이미지가 만들어진다.

그래서 계약이 "아무것도 바뀌지 않는다"에서 "무엇이 바뀌어도 되고
무엇은 안 되는가"로 옮겨 간다. 바뀌어도 되는 것은 image_prompt 하나뿐
이다. 나레이션이 바뀌면 오디오와 타임라인과 자막이 전부 따라 흔들리고,
검색 쿼리가 바뀌면 Pexels가 고르는 사진이 통째로 달라진다 - 둘 다
Stage 3가 하려는 일이 아니다.

특히 검색 쿼리는 조용히 깨지기 쉬운 지점이다. Enrichment는 프롬프트
"뒤에" 덧붙이고 extract_search_query()는 "앞" 8단어만 쓰기 때문에 지금은
안전하지만, 둘 중 하나만 바뀌어도 스톡 사진 선택이 통째로 흔들린다.
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.pipeline import pipeline
from app.services import (
    prompt_enrichment_service,
    prompt_learning_service,
    scene_planner_service,
)
from app.services.search_query_extractor import extract_search_query


SCRIPT = {
    "title": "혈관을 청소하는 아침 습관",
    "hook": "혹시 혈관에 기름때가 꽉 끼는 상상, 해보셨나요?",
    "script": "전체 대본 텍스트",
    "scenes": [
        {
            "scene": 1,
            "narration": "혹시 혈관에 기름때가 꽉 끼는 상상, 해보셨나요?",
            "image_prompt": "Eye-level close-up of a worried middle aged Korean man",
        },
        {
            "scene": 2,
            "narration": "나쁜 LDL 콜레스테롤은 혈관 벽에 쌓여 염증을 일으킵니다.",
            "image_prompt": "Macro view inside a realistic human artery with plaque",
        },
        {
            "scene": 3,
            "narration": "하지만 매일 아침 햇살을 받으며 걷기만 하면 됩니다.",
            "image_prompt": "Low angle wide shot of a serene Korean woman walking",
        },
        {
            "scene": 4,
            "narration": "오늘부터 하루 30분, 당신의 혈관이 달라집니다.",
            "image_prompt": "Over the shoulder shot of a person setting a phone timer",
        },
    ],
}


class PipelineHarness(unittest.TestCase):

    def setUp(self):
        prompt_learning_service.reset_learning()
        self.addCleanup(prompt_learning_service.reset_learning)

    def run_pipeline(self, project_path, stage3):

        captured = {}

        def fake_step01(topic, path):
            data = copy.deepcopy(SCRIPT)
            with open(
                os.path.join(path, "script.json"), "w", encoding="utf-8",
            ) as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return data

        def fake_collect_assets(scenes, path, channel):
            captured["scenes_at_asset_step"] = copy.deepcopy(scenes)
            return scenes

        def fake_tts(scenes, path):
            captured["scenes_at_tts_step"] = copy.deepcopy(scenes)

        with patch.object(config, "ENABLE_SCENE_PLANNER", stage3), \
             patch.object(config, "ENABLE_PROMPT_ENRICHMENT", stage3), \
             patch.object(config, "ENABLE_PROMPT_EFFECTIVENESS", True), \
             patch.object(config, "ENABLE_PROMPT_LEARNING", True), \
             patch.object(config, "ENABLE_AI_DIRECTOR", True), \
             patch.object(config, "ENABLE_PROMPT_OPTIMIZATION", False), \
             patch.object(config, "ENABLE_VIRAL_WRITER", False), \
             patch.object(pipeline.step01_script, "run", fake_step01), \
             patch.object(
                 pipeline.step02_assets, "collect_assets", fake_collect_assets,
             ), \
             patch.object(pipeline.step03_tts, "run", fake_tts), \
             patch.object(pipeline.step04_subtitle, "run", lambda p: None), \
             patch.object(pipeline.step05_video, "run", lambda p: None), \
             patch.object(
                 pipeline.step06_thumbnail, "run", lambda *a, **k: None,
             ), \
             patch.object(
                 pipeline.step07_quality, "run", lambda *a, **k: None,
             ), \
             patch.object(
                 pipeline.regeneration_service, "run", lambda p: None,
             ):

            data = pipeline.run_pipeline(
                topic="혈관 청소",
                project_path=project_path,
                channel="wellbeing",
            )

        return data, captured

    def read_json(self, project_path, name):
        path = os.path.join(project_path, name)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def both(self):
        """stage3 off / on 두 실행 결과를 함께 돌려준다."""

        with tempfile.TemporaryDirectory() as off_dir, \
             tempfile.TemporaryDirectory() as on_dir:

            off, off_captured = self.run_pipeline(off_dir, stage3=False)
            on, on_captured = self.run_pipeline(on_dir, stage3=True)

            return {
                "off": off, "on": on,
                "off_captured": off_captured, "on_captured": on_captured,
                "off_script": self.read_json(off_dir, "script.json"),
                "on_script": self.read_json(on_dir, "script.json"),
                "off_measurements": self.read_json(
                    off_dir, pipeline.MEASUREMENT_FILENAME,
                ),
                "on_measurements": self.read_json(
                    on_dir, pipeline.MEASUREMENT_FILENAME,
                ),
            }


class TestStage3FlagState(unittest.TestCase):

    def test_stage3_engines_stay_disabled_after_the_ab_result(self):
        """Stage 3는 켜서 실제 A/B를 돌린 뒤 되돌렸다.

        같은 대본/같은 오디오로 에셋만 다시 모았고, 실제로 달라진
        이미지는 Imagen이 만드는 2개뿐이었다(나머지 4개는 Pexels이고
        검색어가 안 바뀌어 바이트 동일). 그 2개 중 scene 4가 눈에
        띄게 나빠졌다 - 원본이 "close-up shot"인데 Planner가 "wide
        shot"을 덧붙였고, 결과 이미지에 뜻 없는 가짜 라벨이 박혔다.

        여기 있는 나머지 테스트들은 여전히 의미가 있다. 엔진을 다시
        켤 때 지켜야 할 계약(append-only, 나레이션 불변, 검색어 불변)을
        그대로 고정해 두기 때문이다 - 각 테스트는 플래그를 직접
        patch해서 돌리므로 이 기본값과 무관하게 동작한다.
        """

        self.assertFalse(config.ENABLE_SCENE_PLANNER)
        self.assertFalse(config.ENABLE_PROMPT_ENRICHMENT)

    def test_earlier_stages_remain_enabled(self):
        self.assertTrue(config.ENABLE_PROMPT_EFFECTIVENESS)
        self.assertTrue(config.ENABLE_PROMPT_LEARNING)
        self.assertTrue(config.ENABLE_AI_DIRECTOR)

    def test_later_stages_stay_disabled(self):
        self.assertFalse(config.ENABLE_PROMPT_OPTIMIZATION)
        self.assertFalse(config.ENABLE_VIRAL_WRITER)


class TestCameraConflictIsFixed(unittest.TestCase):
    """Stage 3 A/B가 드러낸 실패를 Sprint69 (Scene Planner v2)가 고쳤다.

    이 클래스는 Sprint68에서 "고쳐지면 실패하도록" 심어 둔 테스트를
    뒤집은 것이다 - 이제는 충돌이 없다는 쪽을 고정한다. 회귀하면
    여기가 먼저 깨진다.
    """

    CONFLICTING = [
        ("Dynamic low-angle close-up shot of running shoes on asphalt",
         3, scene_planner_service.HOOK_CAMERA),
        ("Macro top-down view inside a realistic human artery",
         1, scene_planner_service.HOOK_CAMERA),
        ("Eye-level medium shot of a healthy elderly Korean couple",
         4, scene_planner_service.CTA_CAMERA),
    ]

    def test_planner_adopts_the_camera_already_in_the_prompt(self):
        for prompt, index, expected in self.CONFLICTING:
            with self.subTest(prompt=prompt):
                scenes = [
                    {"scene": n, "narration": "n", "image_prompt": "filler"}
                    for n in range(1, 7)
                ]
                scenes[index]["image_prompt"] = prompt

                plan = scene_planner_service.plan_scenes({"scenes": scenes})

                self.assertEqual(plan[index]["camera"], expected)
                self.assertEqual(
                    plan[index]["camera_source"],
                    scene_planner_service.PROMPT_SOURCE,
                )

    def test_enrichment_no_longer_appends_a_conflicting_camera_phrase(self):
        prompt = "Dynamic low-angle close-up shot of running shoes on asphalt"

        scenes = [
            {"scene": 1, "narration": "n", "image_prompt": prompt},
            {"scene": 2, "narration": "n", "image_prompt": "filler"},
        ]
        plan = scene_planner_service.plan_scenes({"scenes": scenes})

        enriched = prompt_enrichment_service.apply_prompt_enrichment(
            scenes, plan,
        )[0]["image_prompt"]

        self.assertIn("close-up", enriched)
        self.assertNotIn("wide shot", enriched)
        self.assertNotIn("medium shot", enriched)


class TestNarrationAndStructureAreUntouched(PipelineHarness):
    """나레이션이 바뀌면 오디오/타임라인/자막이 전부 따라 흔들린다.
    Stage 3가 손대는 것은 image_prompt 하나여야 한다."""

    def test_narration_is_identical(self):
        result = self.both()

        self.assertEqual(
            [s["narration"] for s in result["off"]["scenes"]],
            [s["narration"] for s in result["on"]["scenes"]],
        )

    def test_scene_count_and_order_are_identical(self):
        result = self.both()

        self.assertEqual(
            [s["scene"] for s in result["off"]["scenes"]],
            [s["scene"] for s in result["on"]["scenes"]],
        )
        self.assertEqual(len(result["on"]["scenes"]), len(SCRIPT["scenes"]))

    def test_visual_type_routing_is_identical(self):
        # real(Pexels) / ai(Imagen) 분기가 달라지면 4개 scene의 에셋이
        # 통째로 바뀐다 - Enrichment가 건드릴 영역이 아니다.
        result = self.both()

        self.assertEqual(
            [s.get("visual_type") for s in result["off"]["scenes"]],
            [s.get("visual_type") for s in result["on"]["scenes"]],
        )


class TestPromptEnrichmentIsAppendOnly(PipelineHarness):

    def test_original_prompt_is_preserved_as_a_prefix(self):
        result = self.both()

        for off_scene, on_scene in zip(
            result["off"]["scenes"], result["on"]["scenes"],
        ):
            self.assertTrue(
                on_scene["image_prompt"].startswith(off_scene["image_prompt"]),
                f"scene {on_scene['scene']}의 원본 프롬프트가 보존되지 않았다:\n"
                f"  off: {off_scene['image_prompt']}\n"
                f"  on : {on_scene['image_prompt']}",
            )

    def test_prompts_gain_descriptors_only_where_the_prompt_was_silent(self):
        # Sprint69 (v2) - 프롬프트가 이미 카메라를 지시하면 문구를
        # 덧붙이지 않는다. 침묵한 scene에만 붙는다.
        result = self.both()

        plan_by_scene = {
            item["scene_id"]: item
            for item in scene_planner_service.plan_scenes(
                {"scenes": SCRIPT["scenes"]}
            )
        }

        for scene in result["on"]["scenes"]:
            plan = plan_by_scene[scene["scene"]]
            camera_phrase = prompt_enrichment_service.CAMERA_PHRASES[
                plan["camera"]
            ]

            if plan["camera_source"] == scene_planner_service.PLANNED_SOURCE:
                self.assertIn(camera_phrase, scene["image_prompt"])
            else:
                added = scene["image_prompt"][
                    len(
                        next(
                            s["image_prompt"]
                            for s in result["off"]["scenes"]
                            if s["scene"] == scene["scene"]
                        )
                    ):
                ]
                self.assertNotIn(camera_phrase, added)

    def test_enrichment_changes_something(self):
        # append-only만 검사하면 "아무것도 안 붙여도 통과"한다.
        result = self.both()

        changed = [
            on_scene["scene"]
            for off_scene, on_scene in zip(
                result["off"]["scenes"], result["on"]["scenes"],
            )
            if off_scene["image_prompt"] != on_scene["image_prompt"]
        ]

        self.assertEqual(len(changed), len(SCRIPT["scenes"]))


class TestStockSearchQueryIsUnaffected(PipelineHarness):
    """4개 중 3~4개 scene은 Pexels 스톡을 쓰고, 그 선택은 오직
    extract_search_query() 결과로 정해진다. Enrichment가 뒤에 붙고
    추출기가 앞 8단어만 쓰기 때문에 지금은 안전하지만, 둘 중 하나만
    바뀌어도 스톡 선택이 통째로 흔들린다."""

    def test_search_query_is_identical_before_and_after_enrichment(self):
        result = self.both()

        for off_scene, on_scene in zip(
            result["off"]["scenes"], result["on"]["scenes"],
        ):
            self.assertEqual(
                extract_search_query(off_scene["image_prompt"]),
                extract_search_query(on_scene["image_prompt"]),
                f"scene {on_scene['scene']}의 스톡 검색 쿼리가 바뀌었다",
            )

    def test_production_length_prompts_keep_their_query(self):
        # 실제 Gemini가 쓰는 프롬프트 길이(내용어 8개 이상)에서는
        # descriptor가 추출 창 밖에 떨어진다. 실제 산출물에서 측정한
        # 프롬프트를 그대로 쓴다.
        production_prompts = [
            "Eye-level close-up of a middle-aged Korean man with a shocked "
            "expression, pointing at a tablet displaying a stark contrast "
            "between a clogged artery and a clean one",
            "Macro top-down view inside a realistic human artery, thick "
            "yellow plaque narrowing the passage, dramatic side lighting",
            "Low angle wide shot of a serene Korean woman in her 50s walking "
            "along a sunlit riverside path in the early morning",
        ]

        plan_item = {
            "camera": scene_planner_service.DEVELOPMENT_CAMERA,
            "visual_type": scene_planner_service.PHOTO_REALISTIC_VISUAL_TYPE,
            "purpose": scene_planner_service.DEVELOPMENT_PURPOSE,
        }

        for prompt in production_prompts:
            enriched = prompt_enrichment_service.enrich_prompt(
                prompt, plan_item,
            )
            self.assertEqual(
                extract_search_query(prompt),
                extract_search_query(enriched),
            )

    def test_a_short_prompt_does_leak_descriptors_into_the_query(self):
        """알려진 한계를 드러내 두는 테스트다 - 고쳐서 지우는 것이 아니라,
        조용히 깨지지 않게 못을 박아 두는 것이 목적이다.

        스톡 검색은 enrichment가 끝난 프롬프트를 그대로 쓰고,
        extract_search_query()는 앞 8개 내용어만 본다. 그래서 내용어가
        8개에 못 미치는 짧은 프롬프트에서는 descriptor가 창 안으로
        밀려 들어와 검색어가 바뀐다.

        실제 대본에서 나오는 프롬프트는 내용어가 15개를 넘어(실측)
        여유가 충분하지만, 그건 여유일 뿐 보장이 아니다. 근본 해결은
        "검색용 프롬프트"와 "생성용 프롬프트"를 분리하는 것이고, 그건
        에셋 선택 동작 자체를 바꾸는 별도 작업이다 - Stage 3에 끼워
        넣으면 A/B의 변수가 둘이 된다.
        """

        short_prompt = "Macro view inside a realistic human artery with plaque"

        enriched = prompt_enrichment_service.enrich_prompt(
            short_prompt,
            {
                "camera": scene_planner_service.DEVELOPMENT_CAMERA,
                "visual_type": (
                    scene_planner_service.PHOTO_REALISTIC_VISUAL_TYPE
                ),
                "purpose": scene_planner_service.DEVELOPMENT_PURPOSE,
            },
        )

        self.assertEqual(
            extract_search_query(short_prompt),
            "macro view inside realistic human artery plaque",
        )
        self.assertEqual(
            extract_search_query(enriched),
            "macro view inside realistic human artery plaque wide",
        )


class TestScenePlanIsProduced(PipelineHarness):

    def test_plan_covers_every_scene_in_order(self):
        result = self.both()

        plan = result["on"]["scene_plan"]

        self.assertEqual(
            [item["scene_id"] for item in plan],
            [scene["scene"] for scene in SCRIPT["scenes"]],
        )

    def test_plan_items_carry_the_expected_fields(self):
        result = self.both()

        for item in result["on"]["scene_plan"]:
            for field in (
                "purpose", "visual_type", "camera",
                "transition", "duration", "keywords",
            ):
                self.assertIn(field, item)

    def test_first_scene_is_hook_and_last_is_cta(self):
        result = self.both()

        plan = result["on"]["scene_plan"]

        self.assertEqual(plan[0]["purpose"], scene_planner_service.HOOK_PURPOSE)
        self.assertEqual(plan[-1]["purpose"], scene_planner_service.CTA_PURPOSE)

    def test_no_plan_is_produced_when_stage3_is_off(self):
        result = self.both()

        self.assertNotIn("scene_plan", result["off"])


class TestMeasurementImproves(PipelineHarness):
    """Stage 1에서 keywords가 항상 0점이던 이유가 scene_plan 부재였다.
    Planner를 켜면 그 10점이 실제로 채워져야 한다 - 안 채워진다면 Planner
    결과가 Effectiveness까지 흘러가지 않는다는 뜻이다."""

    def test_keywords_are_now_measured(self):
        result = self.both()

        off_keywords = [
            entry["metrics"]["keywords"]
            for entry in result["off_measurements"]["prompt_metrics"]
        ]
        on_keywords = [
            entry["metrics"]["keywords"]
            for entry in result["on_measurements"]["prompt_metrics"]
        ]

        self.assertTrue(all(count == 0 for count in off_keywords))
        self.assertTrue(all(count > 0 for count in on_keywords))

    def test_scores_do_not_drop(self):
        result = self.both()

        off_scores = {
            entry["scene_id"]: entry["score"]
            for entry in result["off_measurements"]["prompt_metrics"]
        }
        on_scores = {
            entry["scene_id"]: entry["score"]
            for entry in result["on_measurements"]["prompt_metrics"]
        }

        for scene_id, score in on_scores.items():
            self.assertGreaterEqual(score, off_scores[scene_id])

    def test_learning_now_records_the_planned_patterns(self):
        result = self.both()

        summary = result["on_measurements"]["learning_summary"]

        self.assertTrue(summary["camera_frequency"])
        self.assertTrue(summary["visual_type_frequency"])
        self.assertTrue(summary["purpose_frequency"])
        self.assertTrue(summary["keyword_frequency"])


class TestStage3FailuresNeverBreakProduction(PipelineHarness):

    def _run_with_broken(self, target):
        def boom(*args, **kwargs):
            raise RuntimeError("stage3 exploded")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                getattr(pipeline, target[0]), target[1], boom,
            ):
                data, captured = self.run_pipeline(tmp_dir, stage3=True)
            return data, captured, tmp_dir

    def test_planner_failure_leaves_prompts_untouched(self):
        data, captured, _ = self._run_with_broken(
            ("scene_planner_service", "plan_scenes"),
        )

        self.assertNotIn("scene_plan", data)
        self.assertEqual(len(data["scenes"]), len(SCRIPT["scenes"]))
        self.assertIn("scenes_at_tts_step", captured)

    def test_enrichment_failure_leaves_prompts_untouched(self):
        data, captured, _ = self._run_with_broken(
            ("prompt_enrichment_service", "apply_prompt_enrichment"),
        )

        self.assertEqual(len(data["scenes"]), len(SCRIPT["scenes"]))
        self.assertIn("scenes_at_tts_step", captured)

        # Enrichment가 죽으면 프롬프트는 enrichment 이전 상태 그대로여야
        # 한다 - 절반만 적용된 상태로 넘어가면 안 된다.
        for scene in data["scenes"]:
            self.assertNotIn(", hook", scene["image_prompt"])


if __name__ == "__main__":
    unittest.main()
