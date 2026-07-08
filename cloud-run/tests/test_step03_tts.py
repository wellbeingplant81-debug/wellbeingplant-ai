import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.steps.step03_tts import run


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


if __name__ == "__main__":
    unittest.main()
