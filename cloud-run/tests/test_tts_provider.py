import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.tts_provider import generate_voice, list_voices


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

    def test_elevenlabs_path_applies_voice_quality_pause_markup(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint27 Voice Quality Engine(optimize_for_tts)이 실제로
        # ElevenLabs 호출 경로에 연결되어 있는지 확인한다 - narration
        # 원문이 아니라 pause 마크업이 삽입된 텍스트가 전달돼야 한다.
        os.environ["TTS_PROVIDER"] = "elevenlabs"

        generate_voice("좋은 아침입니다. 시작해볼까요?", "out.mp3")

        called_text = mock_elevenlabs.generate_voice.call_args[0][0]

        self.assertIn('<break time="0.4s" />', called_text)
        self.assertNotEqual(called_text, "좋은 아침입니다. 시작해볼까요?")
        mock_google.generate_voice.assert_not_called()

    def test_google_path_never_receives_pause_markup(
        self, mock_elevenlabs, mock_google,
    ):
        # Google TTS는 <break> 마크업을 해석하지 않고 그대로 읽어버리므로
        # (SynthesisInput(text=...)), 이 마크업이 절대 섞여 들어가면 안 된다.
        os.environ["TTS_PROVIDER"] = "google"

        generate_voice("좋은 아침입니다. 시작해볼까요?", "out.mp3")

        mock_google.generate_voice.assert_called_once_with(
            "좋은 아침입니다. 시작해볼까요?", "out.mp3",
        )
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_google_path_applies_speech_normalization(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint52 - Speech Normalization Engine이 실제로 Google TTS
        # 호출 경로에 연결되어 있는지 확인한다: "2번"이 그대로가 아니라
        # "두 번"으로 바뀐 텍스트가 전달돼야 한다.
        os.environ["TTS_PROVIDER"] = "google"

        generate_voice("밤에 2번 이상 화장실 가세요?", "out.mp3")

        mock_google.generate_voice.assert_called_once_with(
            "밤에 두 번 이상 화장실 가세요?", "out.mp3",
        )
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_elevenlabs_path_does_not_apply_speech_normalization(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint52 범위는 "Google TTS 입력 텍스트만" - ElevenLabs
        # 경로는 이 스프린트에서 건드리지 않는다.
        os.environ["TTS_PROVIDER"] = "elevenlabs"

        generate_voice("2번", "out.mp3")

        called_text = mock_elevenlabs.generate_voice.call_args[0][0]
        self.assertIn("2번", called_text)
        self.assertNotIn("두 번", called_text)


@patch("app.providers.tts_provider.google_tts_provider")
@patch("app.providers.tts_provider.elevenlabs_provider")
class TestTtsProviderListVoicesRouting(unittest.TestCase):

    def setUp(self):
        self._env_patcher = patch.dict(os.environ, {}, clear=False)
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        os.environ.pop("TTS_PROVIDER", None)

    def test_no_env_var_routes_to_google_as_default(
        self, mock_elevenlabs, mock_google,
    ):
        mock_google.list_voices.return_value = ["ko-KR-Chirp3-HD-Aoede"]

        result = list_voices()

        self.assertEqual(result, ["ko-KR-Chirp3-HD-Aoede"])
        mock_google.list_voices.assert_called_once_with()
        mock_elevenlabs.list_voices.assert_not_called()

    def test_provider_elevenlabs_routes_to_elevenlabs(
        self, mock_elevenlabs, mock_google,
    ):
        os.environ["TTS_PROVIDER"] = "elevenlabs"
        mock_elevenlabs.list_voices.return_value = ["Brandon"]

        result = list_voices()

        self.assertEqual(result, ["Brandon"])
        mock_elevenlabs.list_voices.assert_called_once_with()
        mock_google.list_voices.assert_not_called()


if __name__ == "__main__":
    unittest.main()
