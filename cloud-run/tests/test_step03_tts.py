import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.steps.step03_tts import DURATION_OPTIMIZATION_METADATA_FILENAME, run


SAMPLE_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2"},
]

FAKE_SCENE_PATHS = [
    os.path.join("output", "proj", "audio", "scenes", "scene1.mp3"),
    os.path.join("output", "proj", "audio", "scenes", "scene2.mp3"),
]


class TestStep03TtsOptimizesDurationAfterSynthesis(unittest.TestCase):

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_optimize_scene_audio_called_with_scene_paths(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix
    ):
        run(SAMPLE_SCENES, "output/proj")

        mock_optimize.assert_called_once_with(FAKE_SCENE_PATHS)

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_optimize_runs_after_synthesis_and_before_concat(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix
    ):
        call_order = []
        mock_create_tts.side_effect = lambda *a, **k: (
            call_order.append("create_scene_tts") or FAKE_SCENE_PATHS
        )
        mock_optimize.side_effect = lambda *a, **k: call_order.append("optimize_scene_audio")
        mock_concat.side_effect = lambda *a, **k: call_order.append("concat_scene_audio")
        mock_mix.side_effect = lambda *a, **k: call_order.append("mix_audio")

        run(SAMPLE_SCENES, "output/proj")

        self.assertEqual(
            call_order,
            ["create_scene_tts", "optimize_scene_audio", "concat_scene_audio", "mix_audio"],
        )

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_concat_still_receives_same_scene_paths(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix
    ):
        run(SAMPLE_SCENES, "output/proj")

        concat_args = mock_concat.call_args[0]
        self.assertEqual(concat_args[0], FAKE_SCENE_PATHS)


class TestStep03TtsSavesDurationOptimizationMetadata(unittest.TestCase):
    """Sprint61 - Silence-Aware Subtitle Timing. optimize_scene_audio()의
    반환값(마지막 scene에 붙인 무음 길이 등)을 subtitle_service.py가
    나중에 읽을 수 있도록 audio/duration_optimization.json에 저장한다.
    이 저장은 선택적 부가 기능이라 실패해도 파이프라인을 막지 않는다."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_path = os.path.join(self.tmp_dir, "project")
        os.makedirs(os.path.join(self.project_path, "audio"))
        self.metadata_path = os.path.join(
            self.project_path, "audio", DURATION_OPTIMIZATION_METADATA_FILENAME,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_expand_result_is_saved_to_metadata_file(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        mock_optimize.return_value = {
            "action": "expand",
            "original_total": 33.96,
            "final_total": 42.696,
            "pause_seconds": 3.12,
        }

        run(SAMPLE_SCENES, self.project_path)

        with open(self.metadata_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["action"], "expand")
        self.assertEqual(saved["pause_seconds"], 3.12)

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_none_action_is_also_saved(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        mock_optimize.return_value = {
            "action": "none", "original_total": 45.0, "final_total": 45.0,
        }

        run(SAMPLE_SCENES, self.project_path)

        with open(self.metadata_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["action"], "none")

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_non_dict_result_does_not_raise_and_skips_file(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        # optimize_scene_audio()가 예상 밖의 값(dict가 아님)을 반환해도
        # 파이프라인은 계속 진행돼야 한다.
        mock_optimize.return_value = None

        run(SAMPLE_SCENES, self.project_path)  # 예외 없이 끝나야 함

        self.assertFalse(os.path.exists(self.metadata_path))

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_metadata_write_failure_does_not_break_pipeline(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        # project_path/audio 디렉터리가 없는(존재하지 않는 경로) 극단
        # 상황에서도 run() 자체는 예외 없이 끝나야 한다(concat/mix는
        # mock이라 실제 파일시스템 의존이 없음).
        mock_optimize.return_value = {"action": "expand", "pause_seconds": 3.0}

        run(SAMPLE_SCENES, os.path.join(self.tmp_dir, "nonexistent_project"))

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_existing_tests_default_mock_does_not_break_metadata_save(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        # optimize_scene_audio return_value를 지정하지 않으면(기존
        # 다른 테스트들처럼) MagicMock이 반환되는데, 이 경우도 예외
        # 없이 그냥 저장을 건너뛰어야 한다.
        run(SAMPLE_SCENES, self.project_path)

        self.assertFalse(os.path.exists(self.metadata_path))


if __name__ == "__main__":
    unittest.main()
