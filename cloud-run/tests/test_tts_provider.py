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
class TestTtsProviderRouting(unittest.TestCase):

    def setUp(self):
        self._env_patcher = patch.dict(os.environ, {}, clear=False)
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        os.environ.pop("TTS_PROVIDER", None)

    def test_no_env_var_routes_to_google_as_default(
        self, mock_elevenlabs, mock_google,
    ):
        generate_voice("텍스트", "out.mp3")

        mock_google.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_provider_elevenlabs_routes_to_elevenlabs(
        self, mock_elevenlabs, mock_google,
    ):
        os.environ["TTS_PROVIDER"] = "elevenlabs"

        generate_voice("텍스트", "out.mp3")

        mock_elevenlabs.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_google.generate_voice.assert_not_called()

    def test_provider_value_is_case_insensitive(
        self, mock_elevenlabs, mock_google,
    ):
        os.environ["TTS_PROVIDER"] = "ElevenLabs"

        generate_voice("텍스트", "out.mp3")

        mock_elevenlabs.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_google.generate_voice.assert_not_called()

    def test_provider_explicit_google_routes_to_google(
        self, mock_elevenlabs, mock_google,
    ):
        os.environ["TTS_PROVIDER"] = "google"

        generate_voice("텍스트", "out.mp3")

        mock_google.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_unrecognized_provider_value_falls_to_google_default_branch(
        self, mock_elevenlabs, mock_google,
    ):
        os.environ["TTS_PROVIDER"] = "bogus"

        generate_voice("텍스트", "out.mp3")

        mock_google.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_elevenlabs_failure_never_silently_falls_back_to_google(
        self, mock_elevenlabs, mock_google,
    ):
        os.environ["TTS_PROVIDER"] = "elevenlabs"
        mock_elevenlabs.generate_voice.side_effect = Exception("ElevenLabs API 실패")

        with self.assertRaises(Exception):
            generate_voice("텍스트", "out.mp3")

        mock_google.generate_voice.assert_not_called()


if __name__ == "__main__":
    unittest.main()
