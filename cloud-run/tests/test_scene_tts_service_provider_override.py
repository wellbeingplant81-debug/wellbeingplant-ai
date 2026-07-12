"""
Sprint95 (RED) - scene_tts_service.create_scene_tts()의 provider 전달.

create_scene_tts()에 optional 파라미터 provider=None을 추가한다. None이면
지금까지처럼 generate_voice()를 provider 없이 호출하고, 값이 있으면
그대로 generate_voice()에 전달한다. 아직 구현이 없으므로(RED) override
전달 테스트는 실패해야 정상이다.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.scene_tts_service import create_scene_tts


SAMPLE_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1"},
]


class TestSceneTtsServiceProviderOverride(unittest.TestCase):

    @patch("app.services.scene_tts_service.generate_voice")
    def test_no_override_omits_provider_kwarg(self, mock_generate_voice):
        with tempfile.TemporaryDirectory() as tmp_dir:
            create_scene_tts(SAMPLE_SCENES, tmp_dir)

        _, kwargs = mock_generate_voice.call_args
        self.assertNotIn("provider", kwargs)

    @patch("app.services.scene_tts_service.generate_voice")
    def test_override_passed_through_to_generate_voice(self, mock_generate_voice):
        with tempfile.TemporaryDirectory() as tmp_dir:
            create_scene_tts(SAMPLE_SCENES, tmp_dir, provider="elevenlabs")

        _, kwargs = mock_generate_voice.call_args
        self.assertEqual(kwargs.get("provider"), "elevenlabs")


if __name__ == "__main__":
    unittest.main()
