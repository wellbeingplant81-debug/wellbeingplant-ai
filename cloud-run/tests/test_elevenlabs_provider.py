import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers import elevenlabs_provider


def _fake_response(status_code=200, json_data=None, content=b"", text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.content = content
    response.text = text
    return response


class TestResolveVoiceIdByName(unittest.TestCase):

    def setUp(self):
        elevenlabs_provider._voice_id_cache.clear()

    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_finds_matching_voice_case_insensitive(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={"voices": [{"name": "Brandon", "voice_id": "abc123"}]},
        )

        voice_id = elevenlabs_provider._resolve_voice_id_by_name("brandon", "key")

        self.assertEqual(voice_id, "abc123")

    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_voice_not_found_raises(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={"voices": [{"name": "Rachel", "voice_id": "xyz"}]},
        )

        with self.assertRaises(Exception):
            elevenlabs_provider._resolve_voice_id_by_name("Brandon", "key")

    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_non_200_response_raises(self, mock_get):
        mock_get.return_value = _fake_response(status_code=401, text="Unauthorized")

        with self.assertRaises(Exception):
            elevenlabs_provider._resolve_voice_id_by_name("Brandon", "key")

    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_result_is_cached_across_calls(self, mock_get):
        mock_get.return_value = _fake_response(
            json_data={"voices": [{"name": "Brandon", "voice_id": "abc123"}]},
        )

        first = elevenlabs_provider._resolve_voice_id_by_name("Brandon", "key")
        second = elevenlabs_provider._resolve_voice_id_by_name("Brandon", "key")

        self.assertEqual(first, "abc123")
        self.assertEqual(second, "abc123")
        mock_get.assert_called_once()


class TestResolveVoiceId(unittest.TestCase):

    def setUp(self):
        elevenlabs_provider._voice_id_cache.clear()

    @patch.dict(os.environ, {"ELEVENLABS_VOICE_NAME": "Brandon"}, clear=True)
    @patch("app.providers.elevenlabs_provider._resolve_voice_id_by_name")
    def test_uses_name_resolution_when_name_set(self, mock_resolve_by_name):
        mock_resolve_by_name.return_value = "abc123"

        voice_id = elevenlabs_provider._resolve_voice_id("key")

        self.assertEqual(voice_id, "abc123")
        mock_resolve_by_name.assert_called_once_with("Brandon", "key")

    @patch.dict(os.environ, {"ELEVENLABS_VOICE_ID": "direct-id"}, clear=True)
    def test_uses_direct_id_when_name_not_set(self):
        self.assertEqual(elevenlabs_provider._resolve_voice_id("key"), "direct-id")

    @patch.dict(os.environ, {}, clear=True)
    def test_raises_when_neither_set(self):
        with self.assertRaises(Exception):
            elevenlabs_provider._resolve_voice_id("key")

    @patch.dict(
        os.environ,
        {"ELEVENLABS_VOICE_NAME": "Brandon", "ELEVENLABS_VOICE_ID": "direct-id"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider._resolve_voice_id_by_name")
    def test_name_takes_priority_over_direct_id(self, mock_resolve_by_name):
        mock_resolve_by_name.return_value = "from-name"

        voice_id = elevenlabs_provider._resolve_voice_id("key")

        self.assertEqual(voice_id, "from-name")


class TestGenerateVoice(unittest.TestCase):

    def setUp(self):
        elevenlabs_provider._voice_id_cache.clear()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.output_file = os.path.join(self._tmp_dir.name, "voice.mp3")

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises(self):
        with self.assertRaises(Exception):
            elevenlabs_provider.generate_voice("안녕하세요", self.output_file)

    @patch.dict(os.environ, {"ELEVENLABS_API_KEY": "key"}, clear=True)
    def test_missing_voice_config_raises(self):
        with self.assertRaises(Exception):
            elevenlabs_provider.generate_voice("안녕하세요", self.output_file)

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_NAME": "Brandon"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.post")
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_successful_call_uses_resolved_voice_id_and_writes_file(
        self, mock_get, mock_post,
    ):
        mock_get.return_value = _fake_response(
            json_data={"voices": [{"name": "Brandon", "voice_id": "brandon-id"}]},
        )
        mock_post.return_value = _fake_response(content=b"mp3 bytes")

        result = elevenlabs_provider.generate_voice("안녕하세요", self.output_file)

        self.assertEqual(result, self.output_file)
        with open(self.output_file, "rb") as f:
            self.assertEqual(f.read(), b"mp3 bytes")

        called_url = mock_post.call_args[0][0]
        self.assertIn("brandon-id", called_url)

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_ID": "direct-id"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.post")
    def test_non_200_tts_response_raises(self, mock_post):
        mock_post.return_value = _fake_response(status_code=500, text="server error")

        with self.assertRaises(Exception):
            elevenlabs_provider.generate_voice("안녕하세요", self.output_file)

    @patch.dict(
        os.environ,
        {"ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_NAME": "Nonexistent"},
        clear=True,
    )
    @patch("app.providers.elevenlabs_provider.requests.post")
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_unresolved_voice_name_never_falls_back_silently(
        self, mock_get, mock_post,
    ):
        mock_get.return_value = _fake_response(
            json_data={"voices": [{"name": "Brandon", "voice_id": "brandon-id"}]},
        )

        with self.assertRaises(Exception):
            elevenlabs_provider.generate_voice("안녕하세요", self.output_file)

        # 이름을 못 찾았으면 TTS 호출 자체가 절대 일어나면 안 된다
        # (다른 voice로 조용히 대체 금지).
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
