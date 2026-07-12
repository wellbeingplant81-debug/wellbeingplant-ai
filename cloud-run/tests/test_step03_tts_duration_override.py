"""
Sprint94 (RED) - step03_tts.run()의 target_duration/tolerance override 전달.

step03_tts.run()에 optional 파라미터 target_duration/tolerance를
추가한다(기본값 None). None이면 지금까지처럼 optimize_scene_audio()를
scene_audio_paths만으로 호출해(기존 45/2 기본값 그대로) 완전히 동일하게
동작하고, 값이 있으면 그대로 optimize_scene_audio()에 전달한다. 아직
구현이 없으므로(RED) 모든 테스트는 실패해야 정상이다.
"""

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
]

FAKE_SCENE_PATHS = [
    os.path.join("output", "proj", "audio", "scenes", "scene1.mp3"),
]


class TestStep03TtsDurationOverride(unittest.TestCase):

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_no_override_omits_target_duration_kwarg(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        run(SAMPLE_SCENES, "output/proj")

        _, kwargs = mock_optimize.call_args
        self.assertNotIn("target_duration", kwargs)
        self.assertNotIn("tolerance", kwargs)

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_override_passed_through_to_optimizer(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        run(SAMPLE_SCENES, "output/proj", target_duration=55, tolerance=2.0)

        _, kwargs = mock_optimize.call_args
        self.assertEqual(kwargs.get("target_duration"), 55)
        self.assertEqual(kwargs.get("tolerance"), 2.0)


if __name__ == "__main__":
    unittest.main()
