"""
Sprint66 (Stage 1) - 측정 전용 엔진 활성화.

Sprint47 Prompt Effectiveness와 Sprint49 Self-Learning은 "재는 것"만
하는 엔진이다. 켜도 대본/scene/타임라인/오디오/렌더가 조금도 달라지면
안 된다 - 달라진다면 그건 측정이 아니라 개입이다.

문제가 하나 있었다. pipeline.py는 prompt_metrics를 project_data에 넣은
뒤 그 dict를 통째로 script.json에 쓴다. 그래서 플래그를 켜는 것만으로
script.json 바이트가 바뀐다. 측정 산출물(Observability)과 생성
산출물(Production)은 같은 파일에 섞이면 안 되므로 분리한다.

여기 테스트들은 그 경계를 고정한다.
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
from app.services import prompt_learning_service


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
    """외부 서비스(Gemini/Imagen/TTS/ffmpeg)를 전부 걷어내고 파이프라인의
    데이터 흐름만 남긴다. 플래그가 그 흐름을 바꾸는지 보기 위함이다."""

    def setUp(self):
        prompt_learning_service.reset_learning()
        self.addCleanup(prompt_learning_service.reset_learning)

    def run_pipeline(self, project_path, effectiveness, learning):

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

        with patch.object(config, "ENABLE_PROMPT_EFFECTIVENESS", effectiveness), \
             patch.object(config, "ENABLE_PROMPT_LEARNING", learning), \
             patch.object(config, "ENABLE_SCENE_PLANNER", False), \
             patch.object(config, "ENABLE_PROMPT_ENRICHMENT", False), \
             patch.object(config, "ENABLE_PROMPT_OPTIMIZATION", False), \
             patch.object(config, "ENABLE_VIRAL_WRITER", False), \
             patch.object(config, "ENABLE_AI_DIRECTOR", False), \
             patch.object(pipeline.step01_script_resolve, "run", fake_step01), \
             patch.object(
                 pipeline.step02_asset_resolve, "run", fake_collect_assets,
             ), \
             patch.object(pipeline.step03_tts, "run", fake_tts), \
             patch.object(pipeline.step04_subtitle, "run", lambda p: None), \
             patch.object(pipeline.step05_video, "run", lambda p: None), \
             patch.object(
                 pipeline.step06_thumbnail, "run",
                 lambda *args, **kwargs: None,
             ), \
             patch.object(
                 pipeline.step07_quality, "run",
                 lambda *args, **kwargs: None,
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


class TestStage1FlagsOnly(unittest.TestCase):

    def test_only_the_two_measurement_engines_are_enabled(self):
        self.assertTrue(config.ENABLE_PROMPT_EFFECTIVENESS)
        self.assertTrue(config.ENABLE_PROMPT_LEARNING)

    def test_engines_not_yet_activated_stay_disabled(self):
        # 아직 어느 스테이지에서도 켜지 않은 엔진들.
        #
        # Sprint67 - AI Director는 여기 없다. 켜져 있어도 scene을 바꾸지
        # 않는 관측 전용 엔진이고, 계약은 test_stage2_ai_director.py가
        # 고정한다.
        #
        # Sprint68 - Scene Planner와 Prompt Enrichment도 여기서 빠졌다.
        # 이 둘은 Stage 3에서 켰고 실제로 image_prompt를 바꾼다. 그래서
        # 이 파일의 "출력 불변" 검증은 config 기본값이 아니라
        # run_pipeline() 하네스가 직접 둘을 끄는 것으로 성립시킨다.
        self.assertFalse(config.ENABLE_PROMPT_OPTIMIZATION)
        self.assertFalse(config.ENABLE_VIRAL_WRITER)


class TestScriptJsonIsUnchanged(PipelineHarness):

    def test_script_json_is_byte_identical_with_and_without_the_engines(self):
        with tempfile.TemporaryDirectory() as off_dir, \
             tempfile.TemporaryDirectory() as on_dir:

            self.run_pipeline(off_dir, effectiveness=False, learning=False)
            self.run_pipeline(on_dir, effectiveness=True, learning=True)

            self.assertEqual(
                self.read(off_dir, "script.json"),
                self.read(on_dir, "script.json"),
                "측정 엔진을 켰다고 script.json이 달라지면 안 된다",
            )

    def test_script_json_never_contains_measurement_keys(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, effectiveness=True, learning=True)

            saved = json.loads(
                self.read(tmp_dir, "script.json").decode("utf-8")
            )

            for key in pipeline.MEASUREMENT_ONLY_KEYS:
                self.assertNotIn(key, saved)

            self.assertEqual(
                list(saved), ["title", "hook", "script", "scenes"],
            )


class TestGenerationInputsAreUnchanged(PipelineHarness):

    def test_scenes_handed_to_every_later_step_are_identical(self):
        with tempfile.TemporaryDirectory() as off_dir, \
             tempfile.TemporaryDirectory() as on_dir:

            _, off = self.run_pipeline(off_dir, False, False)
            _, on = self.run_pipeline(on_dir, True, True)

            self.assertEqual(
                off["scenes_at_asset_step"], on["scenes_at_asset_step"],
            )
            self.assertEqual(
                off["scenes_at_tts_step"], on["scenes_at_tts_step"],
            )

    def test_image_prompts_are_identical_with_and_without_the_engines(self):
        # visual_consistency_engine(플래그와 무관하게 항상 동작)이
        # 채널 스타일을 덧붙이므로 원본과는 당연히 다르다. 여기서 봐야
        # 할 것은 "측정 엔진을 켠다고 달라지는가"뿐이다.
        with tempfile.TemporaryDirectory() as off_dir, \
             tempfile.TemporaryDirectory() as on_dir:

            off, _ = self.run_pipeline(off_dir, False, False)
            on, _ = self.run_pipeline(on_dir, True, True)

            self.assertEqual(
                [scene["image_prompt"] for scene in off["scenes"]],
                [scene["image_prompt"] for scene in on["scenes"]],
            )

    def test_narration_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            data, _ = self.run_pipeline(tmp_dir, True, True)

            self.assertEqual(
                [scene["narration"] for scene in data["scenes"]],
                [scene["narration"] for scene in SCRIPT["scenes"]],
            )


class TestMeasurementsAreRecorded(PipelineHarness):

    def test_metrics_file_is_written_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, True, True)

            raw = self.read(tmp_dir, pipeline.MEASUREMENT_FILENAME)
            self.assertIsNotNone(raw, "측정 결과 파일이 없습니다")

            saved = json.loads(raw.decode("utf-8"))

            self.assertEqual(
                len(saved["prompt_metrics"]), len(SCRIPT["scenes"]),
            )

            for entry in saved["prompt_metrics"]:
                self.assertIn("scene_id", entry)
                self.assertIn("score", entry)
                self.assertIn("passed", entry)
                self.assertIn("metrics", entry)

    def test_metrics_file_is_absent_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, False, False)

            self.assertIsNone(
                self.read(tmp_dir, pipeline.MEASUREMENT_FILENAME),
            )

    def test_learning_summary_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            self.run_pipeline(tmp_dir, True, True)

            saved = json.loads(
                self.read(tmp_dir, pipeline.MEASUREMENT_FILENAME).decode("utf-8")
            )

            summary = saved["learning_summary"]

            self.assertGreater(
                summary["success_count"], 0,
                "PASS한 scene이 하나도 학습되지 않았습니다",
            )
            self.assertGreater(summary["average_score"], 0)

    def test_learning_ignores_scenes_that_did_not_pass(self):
        # "실패한 프롬프트는 배우지 않는다" 원칙이 파이프라인 경로에서도
        # 지켜지는지 확인한다.
        with tempfile.TemporaryDirectory() as tmp_dir:

            with patch.object(
                pipeline.prompt_effectiveness_service, "evaluate_scenes",
                lambda *args: [
                    {"scene_id": 1, "score": 10, "passed": False, "metrics": {}},
                    {"scene_id": 2, "score": 95, "passed": True, "metrics": {}},
                    {"scene_id": 3, "score": 20, "passed": False, "metrics": {}},
                ],
            ):
                self.run_pipeline(tmp_dir, True, True)

            saved = json.loads(
                self.read(tmp_dir, pipeline.MEASUREMENT_FILENAME).decode("utf-8")
            )

            self.assertEqual(saved["learning_summary"]["success_count"], 1)


class TestObservabilityNeverBreaksProduction(PipelineHarness):
    """Quality Engine은 Observability Layer다 - 여기서 무슨 일이 나든
    영상 생성은 끝까지 진행되어야 한다."""

    def test_effectiveness_failure_does_not_stop_the_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            def boom(*args, **kwargs):
                raise RuntimeError("measurement exploded")

            with patch.object(
                pipeline.prompt_effectiveness_service, "evaluate_scenes", boom,
            ):
                data, captured = self.run_pipeline(tmp_dir, True, True)

            self.assertEqual(len(data["scenes"]), len(SCRIPT["scenes"]))
            self.assertIn("scenes_at_tts_step", captured)
            self.assertIsNotNone(self.read(tmp_dir, "script.json"))

    def test_learning_failure_does_not_stop_the_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            def boom(*args, **kwargs):
                raise RuntimeError("learning exploded")

            with patch.object(
                pipeline.prompt_learning_service, "learn_from_scenes", boom,
            ):
                data, captured = self.run_pipeline(tmp_dir, True, True)

            self.assertEqual(len(data["scenes"]), len(SCRIPT["scenes"]))
            self.assertIn("scenes_at_tts_step", captured)

    def test_unwritable_measurement_file_does_not_stop_the_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:

            def boom(*args, **kwargs):
                raise OSError("disk on fire")

            with patch.object(pipeline, "_write_measurements", boom):
                data, captured = self.run_pipeline(tmp_dir, True, True)

            self.assertEqual(len(data["scenes"]), len(SCRIPT["scenes"]))
            self.assertIn("scenes_at_tts_step", captured)
            self.assertIsNotNone(self.read(tmp_dir, "script.json"))


if __name__ == "__main__":
    unittest.main()
