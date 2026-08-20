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
from app.services import audio_policy


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

        # Sprint244 - 이 묶음은 **유료 Provider 자신의 동작**을 잰다.
        # 고른 voice_id 를 쓰는가, 응답을 정책 오디오 포맷으로 바꾸는가.
        #
        # 그 자리에 관문이 생겼다 - 고르지 않은 유료는 부르지 않는다.
        # 여기서 재려는 것은 관문 뒤의 일이므로 그 전제를 적는다.
        # 실제 API 는 이 파일이 이미 mock 으로 막아 두었다.
        from app.services import voice_policy

        gate = patch.object(voice_policy, "require_allowed", lambda *a: None)
        gate.start()
        self.addCleanup(gate.stop)
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.output_file = os.path.join(self._tmp_dir.name, "voice.wav")

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
    @patch("app.providers.elevenlabs_provider.subprocess.run")
    @patch("app.providers.elevenlabs_provider.requests.post")
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_successful_call_uses_resolved_voice_id_and_writes_file(
        self, mock_get, mock_post, mock_run,
    ):
        mock_get.return_value = _fake_response(
            json_data={"voices": [{"name": "Brandon", "voice_id": "brandon-id"}]},
        )
        mock_post.return_value = _fake_response(content=b"mp3 bytes")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = elevenlabs_provider.generate_voice("안녕하세요", self.output_file)

        self.assertEqual(result, self.output_file)

        called_url = mock_post.call_args[0][0]
        self.assertIn("brandon-id", called_url)

    @patch("app.providers.elevenlabs_provider.subprocess.run")
    @patch("app.providers.elevenlabs_provider.requests.post")
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_response_is_normalized_to_policy_audio_format(
        self, mock_get, mock_post, mock_run,
    ):
        """Sprint63 - ElevenLabs는 MP3를 돌려주지만 파이프라인 나머지
        구간은 무손실 PCM만 다룬다. 받은 바이트를 그대로 .wav 이름으로
        저장하면 컨테이너와 내용이 어긋나므로, 여기서 한 번 디코딩해
        정책 포맷으로 정규화해야 한다."""

        mock_get.return_value = _fake_response(
            json_data={"voices": [{"name": "Brandon", "voice_id": "brandon-id"}]},
        )
        mock_post.return_value = _fake_response(content=b"mp3 bytes")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        elevenlabs_provider.generate_voice("안녕하세요", self.output_file)

        command = mock_run.call_args[0][0]

        # Sprint169 - 이름 대신 실제 자리를 부른다. 부르는 도구는
        # 그대로이므로 경로 안에 그 이름이 있는지를 본다.
        self.assertIn("ffmpeg", os.path.basename(command[0]).lower())
        self.assertIn(audio_policy.NARRATION_PCM_CODEC, command)
        self.assertIn(str(audio_policy.NARRATION_SAMPLE_RATE_HZ), command)
        self.assertEqual(command[-1], self.output_file)

    @patch("app.providers.elevenlabs_provider.subprocess.run")
    @patch("app.providers.elevenlabs_provider.requests.post")
    @patch("app.providers.elevenlabs_provider.requests.get")
    def test_conversion_failure_raises_instead_of_writing_bad_audio(
        self, mock_get, mock_post, mock_run,
    ):
        mock_get.return_value = _fake_response(
            json_data={"voices": [{"name": "Brandon", "voice_id": "brandon-id"}]},
        )
        mock_post.return_value = _fake_response(content=b"not audio")
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        with self.assertRaises(Exception):
            elevenlabs_provider.generate_voice("안녕하세요", self.output_file)

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
