"""
Sprint95 (RED) - step03_tts.run()의 tts_provider override 전달.

step03_tts.run()에 optional 파라미터 tts_provider=None을 추가한다.
None이면 지금까지처럼 create_scene_tts()를 provider 없이 호출하고,
값이 있으면 그대로 create_scene_tts()에 provider=로 전달한다. 아직
구현이 없으므로(RED) override 전달 테스트는 실패해야 정상이다.
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


class TestStep03TtsProviderOverride(unittest.TestCase):

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_no_override_omits_provider_kwarg(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        run(SAMPLE_SCENES, "output/proj")

        _, kwargs = mock_create_tts.call_args
        self.assertNotIn("provider", kwargs)

    @patch("app.steps.step03_tts.mix_audio")
    @patch("app.steps.step03_tts.concat_scene_audio")
    @patch("app.steps.step03_tts.optimize_scene_audio")
    @patch("app.steps.step03_tts.create_scene_tts", return_value=FAKE_SCENE_PATHS)
    def test_tts_provider_passed_through_to_create_scene_tts(
        self, mock_create_tts, mock_optimize, mock_concat, mock_mix,
    ):
        run(SAMPLE_SCENES, "output/proj", tts_provider="elevenlabs")

        _, kwargs = mock_create_tts.call_args
        self.assertEqual(kwargs.get("provider"), "elevenlabs")


if __name__ == "__main__":
    unittest.main()
