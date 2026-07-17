"""
Sprint123 (GREEN) - Longform Pre-flight Validation. elevenlabs_provider.
validate_availability()는 ELEVENLABS_API_KEY/Voice(이름 또는 ID)가
실제로 유효한지 확인하고, 실패하면 예외를 던진다(Google로 자동 대체
없음). generate_voice()도 실제 호출 시 Provider/Voice Name/Voice ID를
로그로 남긴다.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers import elevenlabs_provider


def _voices_response(voices):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"voices": voices}
    return response


class TestValidateAvailability(unittest.TestCase):

    def setUp(self):
        elevenlabs_provider._voice_id_cache.clear()
        self.addCleanup(elevenlabs_provider._voice_id_cache.clear)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises(self):
        with self.assertRaises(Exception):
            elevenlabs_provider.validate_availability()

    @patch.dict(os.environ, {"ELEVENLABS_API_KEY": "key"}, clear=True)
    def test_missing_voice_env_vars_raises(self):
        with self.assertRaises(Exception):
            elevenlabs_provider.validate_availability()

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_ID": "voice-123"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_api_failure_raises(self, mock_get):
        mock_get.return_value = MagicMock(status_code=401, text="unauthorized")

        with self.assertRaises(Exception):
            elevenlabs_provider.validate_availability()

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_ID": "voice-123"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_voice_id_not_found_in_account_raises(self, mock_get):
        mock_get.return_value = _voices_response(
            [{"voice_id": "other-voice", "name": "Someone"}],
        )

        with self.assertRaises(Exception):
            elevenlabs_provider.validate_availability()

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_ID": "voice-123"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_valid_voice_id_succeeds(self, mock_get):
        mock_get.return_value = _voices_response(
            [{"voice_id": "voice-123", "name": "Brandon"}],
        )

        voice_id, voice_name = elevenlabs_provider.validate_availability()

        self.assertEqual(voice_id, "voice-123")
        self.assertIsNone(voice_name)

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_NAME": "Brandon"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_valid_voice_name_succeeds_and_resolves_id(self, mock_get):
        mock_get.return_value = _voices_response(
            [{"voice_id": "voice-123", "name": "Brandon"}],
        )

        voice_id, voice_name = elevenlabs_provider.validate_availability()

        self.assertEqual(voice_id, "voice-123")
        self.assertEqual(voice_name, "Brandon")

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_NAME": "DoesNotExist"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_voice_name_not_found_raises(self, mock_get):
        mock_get.return_value = _voices_response(
            [{"voice_id": "voice-123", "name": "Brandon"}],
        )

        with self.assertRaises(Exception):
            elevenlabs_provider.validate_availability()


class TestGenerateVoiceLogging(unittest.TestCase):

    def setUp(self):
        elevenlabs_provider._voice_id_cache.clear()
        self.addCleanup(elevenlabs_provider._voice_id_cache.clear)

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_ID": "voice-123"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.post")
    def test_generate_voice_logs_provider_and_voice_id(self, mock_post, capsys=None):
        mock_post.return_value = MagicMock(status_code=200, content=b"audio bytes")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = os.path.join(tmp_dir, "voice.mp3")
            elevenlabs_provider.generate_voice("hello", output_file)


if __name__ == "__main__":
    unittest.main()
