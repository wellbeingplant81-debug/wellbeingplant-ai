import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers import google_tts_provider


class TestListVoices(unittest.TestCase):

    @patch("app.providers.google_tts_provider.texttospeech.TextToSpeechClient")
    def test_returns_voice_names_for_default_korean_locale(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        voice_a = MagicMock()
        voice_a.name = "ko-KR-Chirp3-HD-Aoede"
        voice_b = MagicMock()
        voice_b.name = "ko-KR-Standard-A"
        mock_client.list_voices.return_value = MagicMock(voices=[voice_a, voice_b])

        voices = google_tts_provider.list_voices()

        mock_client.list_voices.assert_called_once_with(language_code="ko-KR")
        self.assertEqual(voices, ["ko-KR-Chirp3-HD-Aoede", "ko-KR-Standard-A"])

    @patch("app.providers.google_tts_provider.texttospeech.TextToSpeechClient")
    def test_accepts_explicit_language_code(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.list_voices.return_value = MagicMock(voices=[])

        google_tts_provider.list_voices(language_code="en-US")

        mock_client.list_voices.assert_called_once_with(language_code="en-US")


if __name__ == "__main__":
    unittest.main()
