"""
Sprint67 (Stage 2) - AI Director 활성화.

Director는 다른 엔진들의 결과를 읽어 scene마다 accept/review/regenerate
권고만 계산한다. LLM도, DB도, 파일 I/O도 없고 scene을 건드리지도
않는다 - Stage 1의 두 엔진과 같은 부류의 관측 전용 엔진이다.

그래서 Stage 1과 같은 계약이 그대로 적용된다: 켜도 생성 산출물은
바이트 하나 달라지지 않고, 결정은 측정 artifact에만 남는다.

주의할 점이 하나 있었다. Stage 1에서 넣은 측정 기록 블록이 Director
블록보다 앞에 있어서, 그대로 켜면 director_decision이 파일에는 안
남고 script.json에만 실린다. 기록 시점을 Director 뒤로 옮긴다.
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
from app.services import ai_director_service, prompt_learning_service


SCRIPT = {
    "title": "혈관을 청소하는 아침 습관",
    "hook": "혹시 혈관에 기름때가 꽉 끼는 상상, 해보셨나요?",
    "script": "전체 대본 텍스트",
    "scenes": [
        {
            "scene": 1,
            "narration": "혹시 혈관에 기름때가 꽉 끼는 상상, 해보셨나요?",
            "image_prompt": "A close-up portrait of a worried middle aged man",
        },
        {
            "scene": 2,
            "narration": "나쁜 LDL 콜레스테롤은 혈관 벽에 쌓여 염증을 일으킵니다.",
            "image_prompt": "Medical illustration of a narrowed blood vessel",
        },
        {
            "scene": 3,
            "narration": "하지만 매일 아침 햇살을 받으며 걷기만 하면 됩니다.",
            "image_prompt": "A calm morning walk in a sunlit park",
        },
    ],
}


class PipelineHarness(unittest.TestCase):

    def setUp(self):
        prompt_learning_service.reset_learning()
        self.addCleanup(prompt_learning_service.reset_learning)

    def run_pipeline(self, project_path, director, measurement=True):

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

        with patch.object(config, "ENABLE_AI_DIRECTOR", director), \
             patch.object(
                 config, "ENABLE_PROMPT_EFFECTIVENESS", measurement,
             ), \
             patch.object(config, "ENABLE_PROMPT_LEARNING", measurement), \
             patch.object(config, "ENABLE_SCENE_PLANNER", False), \
             patch.object(config, "ENABLE_PROMPT_ENRICHMENT", False), \
             patch.object(config, "ENABLE_PROMPT_OPTIMIZATION", False), \
             patch.object(config, "ENABLE_VIRAL_WRITER", False), \
             patch.object(pipeline.step01_script_resolve, "run", fake_step01), \
             patch.object(
                 pipeline.step02_asset_resolve, "run", fake_collect_assets,
             ), \
             patch.object(pipeline.step03_voice_resolve, "run", fake_tts), \
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

    def read(self, project_path, name):
        path = os.path.join(project_path, name)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def measurements(self, project_path):
        raw = self.read(project_path, pipeline.MEASUREMENT_FILENAME)
        return json.loads(raw.decode("utf-8")) if raw else None


class TestStage2FlagState(unittest.TestCase):

    def test_director_is_enabled(self):
        self.assertTrue(config.ENABLE_AI_DIRECTOR)

    def test_stage1_engines_remain_enabled(self):
        self.assertTrue(config.ENABLE_PROMPT_EFFECTIVENESS)
        self.assertTrue(config.ENABLE_PROMPT_LEARNING)

    def test_engines_not_yet_activated_stay_disabled(self):
        # Sprint68 - Scene Planner와 Prompt Enrichment는 Stage 3에서
        # 켰다. 이 파일의 "출력 불변" 검증은 config 기본값이 아니라
        # run_pipeline() 하네스가 직접 둘을 끄는 것으로 성립시킨다.
        self.assertFalse(config.ENABLE_PROMPT_OPTIMIZATION)
        self.assertFalse(config.ENABLE_VIRAL_WRITER)


class TestDecisionNeverReachesScriptJson(PipelineHarness):

    def test_director_decision_is_a_measurement_key(self):
        self.assertIn("director_decision", pipeline.MEASUREMENT_ONLY_KEYS)

    def test_script_json_is_byte_identical_with_and_without_the_director(self):
        with tempfile.TemporaryDirectory() as off_dir, \
             tempfile.TemporaryDirectory() as on_dir:

            self.run_pipeline(off_dir, director=False)
            self.run_pipeline(on_dir, director=True)

            self.assertEqual(
                self.read(off_dir, "script.json"),
                self.read(on_dir, "script.json"),
            )

    def test_script_json_never_contains_the_decision(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, director=True)

            saved = json.loads(
                self.read(tmp_dir, "script.json").decode("utf-8")
            )

            self.assertNotIn("director_decision", saved)
            self.assertEqual(
                list(saved), ["title", "hook", "script", "scenes"],
            )


class TestGenerationInputsAreUnchanged(PipelineHarness):

    def test_scenes_handed_to_every_later_step_are_identical(self):
        with tempfile.TemporaryDirectory() as off_dir, \
             tempfile.TemporaryDirectory() as on_dir:

            _, off = self.run_pipeline(off_dir, director=False)
            _, on = self.run_pipeline(on_dir, director=True)

            self.assertEqual(
                off["scenes_at_asset_step"], on["scenes_at_asset_step"],
            )
            self.assertEqual(
                off["scenes_at_tts_step"], on["scenes_at_tts_step"],
            )


class TestDecisionIsRecorded(PipelineHarness):

    def test_decision_is_written_to_the_measurement_artifact(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, director=True)

            saved = self.measurements(tmp_dir)
            self.assertIsNotNone(saved)

            decisions = saved["director_decision"]
            self.assertEqual(len(decisions), len(SCRIPT["scenes"]))

            for entry in decisions:
                self.assertIn("scene_id", entry)
                self.assertIn(
                    entry["decision"],
                    (
                        ai_director_service.ACCEPT,
                        ai_director_service.REVIEW,
                        ai_director_service.REGENERATE,
                    ),
                )
                self.assertGreaterEqual(entry["confidence"], 0.0)
                self.assertLessEqual(entry["confidence"], 1.0)
                self.assertTrue(entry["reasons"])

    def test_decision_is_absent_when_the_director_is_off(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, director=False)

            saved = self.measurements(tmp_dir)
            self.assertNotIn("director_decision", saved or {})

    def test_metrics_and_decision_share_one_artifact(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, director=True)

            saved = self.measurements(tmp_dir)

            self.assertIn("prompt_metrics", saved)
            self.assertIn("director_decision", saved)
            self.assertIn("learning_summary", saved)

    def test_decision_is_recorded_even_without_prompt_metrics(self):
        # Effectiveness가 꺼져 있어도 Director만으로 기록이 남아야 한다 -
        # 기록 조건이 prompt_metrics 유무에 묶여 있으면 안 된다.
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, director=True, measurement=False)

            saved = self.measurements(tmp_dir)

            self.assertIsNotNone(saved)
            self.assertIn("director_decision", saved)
            self.assertNotIn("prompt_metrics", saved)


class TestDecisionQuality(PipelineHarness):
    """Stage 1과 마찬가지로, 지금 나오는 결정이 어떤 근거 위에 서 있는지
    분명히 해 둔다. asset_quality_results는 아직 파이프라인에 연결되어
    있지 않으므로 asset 쪽은 항상 unknown이다."""

    def test_every_scene_gets_exactly_one_decision(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, director=True)

            decisions = self.measurements(tmp_dir)["director_decision"]

            self.assertEqual(
                [entry["scene_id"] for entry in decisions],
                [scene["scene"] for scene in SCRIPT["scenes"]],
            )

    def test_asset_quality_is_reported_as_unknown_while_unwired(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, director=True)

            decisions = self.measurements(tmp_dir)["director_decision"]

            for entry in decisions:
                self.assertIn(
                    ai_director_service.ASSET_QUALITY_UNKNOWN,
                    entry["reasons"],
                )

    def test_passing_prompts_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, director=True)

            decisions = self.measurements(tmp_dir)["director_decision"]

            for entry in decisions:
                self.assertEqual(entry["decision"], ai_director_service.ACCEPT)
                self.assertIn(
                    ai_director_service.PROMPT_PASSED, entry["reasons"],
                )

    def test_failing_prompts_are_marked_for_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            with patch.object(
                pipeline.prompt_effectiveness_service, "evaluate_scenes",
                lambda *args: [
                    {"scene_id": 1, "score": 10, "passed": False, "metrics": {}},
                    {"scene_id": 2, "score": 95, "passed": True, "metrics": {}},
                    {"scene_id": 3, "score": 20, "passed": False, "metrics": {}},
                ],
            ):
                self.run_pipeline(tmp_dir, director=True)

            decisions = {
                entry["scene_id"]: entry
                for entry in self.measurements(tmp_dir)["director_decision"]
            }

            self.assertEqual(
                decisions[1]["decision"], ai_director_service.REGENERATE,
            )
            self.assertEqual(
                decisions[2]["decision"], ai_director_service.ACCEPT,
            )
            self.assertEqual(
                decisions[3]["decision"], ai_director_service.REGENERATE,
            )


class TestDirectorFailureNeverBreaksProduction(PipelineHarness):

    def test_director_exception_does_not_stop_the_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            def boom(*args, **kwargs):
                raise RuntimeError("director exploded")

            with patch.object(
                pipeline.ai_director_service, "evaluate_scenes", boom,
            ):
                data, captured = self.run_pipeline(tmp_dir, director=True)

            self.assertEqual(len(data["scenes"]), len(SCRIPT["scenes"]))
            self.assertIn("scenes_at_tts_step", captured)
            self.assertIsNotNone(self.read(tmp_dir, "script.json"))

    def test_no_partial_decision_survives_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            def boom(*args, **kwargs):
                raise RuntimeError("director exploded")

            with patch.object(
                pipeline.ai_director_service, "evaluate_scenes", boom,
            ):
                data, _ = self.run_pipeline(tmp_dir, director=True)

            self.assertNotIn("director_decision", data)
            self.assertNotIn(
                "director_decision", self.measurements(tmp_dir) or {},
            )

    def test_production_output_is_unaffected_by_a_director_failure(self):
        with tempfile.TemporaryDirectory() as healthy_dir, \
             tempfile.TemporaryDirectory() as broken_dir:

            self.run_pipeline(healthy_dir, director=True)

            def boom(*args, **kwargs):
                raise RuntimeError("director exploded")

            with patch.object(
                pipeline.ai_director_service, "evaluate_scenes", boom,
            ):
                self.run_pipeline(broken_dir, director=True)

            self.assertEqual(
                self.read(healthy_dir, "script.json"),
                self.read(broken_dir, "script.json"),
            )


if __name__ == "__main__":
    unittest.main()
