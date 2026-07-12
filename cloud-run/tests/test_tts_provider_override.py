"""
Sprint95 (RED) - tts_provider.generate_voice()의 provider override.

generate_voice()에 optional 파라미터 provider=None을 추가한다. None이면
지금까지처럼 os.getenv("TTS_PROVIDER", "google")을 읽고(기존
test_tts_provider.py의 env-var 라우팅 테스트는 그대로 유지되어야
한다), 값이 주어지면 env var보다 우선한다. 아직 구현이 없으므로(RED)
override 관련 테스트는 실패해야 정상이다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.tts_provider import generate_voice


@patch("app.providers.tts_provider.google_tts_provider")
@patch("app.providers.tts_provider.elevenlabs_provider")
class TestTtsProviderOverride(unittest.TestCase):

    def setUp(self):
        self._env_patcher = patch.dict(os.environ, {}, clear=False)
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        os.environ.pop("TTS_PROVIDER", None)

    def test_no_override_falls_back_to_env_var(self, mock_elevenlabs, mock_google):
        os.environ["TTS_PROVIDER"] = "elevenlabs"

        generate_voice("텍스트", "out.mp3")

        mock_elevenlabs.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_google.generate_voice.assert_not_called()

    def test_override_takes_precedence_over_env_var(self, mock_elevenlabs, mock_google):
        os.environ["TTS_PROVIDER"] = "google"

        generate_voice("텍스트", "out.mp3", provider="elevenlabs")

        mock_elevenlabs.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_google.generate_voice.assert_not_called()

    def test_override_non_elevenlabs_value_routes_to_google(self, mock_elevenlabs, mock_google):
        # "chirp"는 provider 셀렉터 값이 아니라 development profile의
        # 표기일 뿐 - 기존 분기(비-elevenlabs는 전부 google)가 그대로
        # 적용되는지만 확인한다. 이 라우팅 결과 자체는 구현 세부사항.
        os.environ["TTS_PROVIDER"] = "elevenlabs"

        generate_voice("텍스트", "out.mp3", provider="chirp")

        mock_google.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_elevenlabs.generate_voice.assert_not_called()


if __name__ == "__main__":
    unittest.main()
