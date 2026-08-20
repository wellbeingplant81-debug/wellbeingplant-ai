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

    def test_no_env_var_never_routes_to_a_paid_provider(
        self, mock_elevenlabs, mock_google,
    ):
        """
        Sprint244 - 이 자리는 예전에 반대를 잠그고 있었다.

        "환경변수가 없으면 Google 로 간다" 가 이 시험의 이름이자
        주장이었다. 즉 아무것도 고르지 않은 사람이 가장 비싼 길로
        가는 것을 계약으로 지키고 있었다. 실제로 그렇게 요금이 나갔다.

        같은 함수를 계속 지킨다. 지키는 방향만 뒤집는다.
        """

        from app.providers import local_voice_provider

        # 무료 쪽은 녹음이 없으면 거절한다. 그것이 이 시험의 관심사는
        # 아니므로 지나가게 두고, 재는 것은 유료가 불렸는가 하나다.
        with patch.object(local_voice_provider, "generate_voice",
                          return_value="out.mp3"):
            generate_voice("텍스트", "out.mp3")

        mock_google.generate_voice.assert_not_called()
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_provider_elevenlabs_routes_to_elevenlabs(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint244 - 고른 사실을 인자로 적는다.
        #
        # 예전에는 TTS_PROVIDER 로 골랐다. 이제 그 환경변수는 유료를
        # 고르지 못한다 - 고르지 않은 사람이 요금을 무는 길이었기
        # 때문이다. 고르는 자리는 화면이고, 그것이 닿는 곳이 이 인자다
        # (Sprint125 가 같은 이유로 만들어 두었다).
        #
        # 이 시험이 재는 것은 그대로다: 고른 뒤에 글이 어떻게 다듬어져
        # 어느 쪽으로 가는가.
        generate_voice("텍스트", "out.mp3", provider="elevenlabs")

        mock_elevenlabs.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_google.generate_voice.assert_not_called()

    def test_provider_value_is_case_insensitive(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint244 - 고른 사실을 인자로 적는다.
        #
        # 예전에는 TTS_PROVIDER 로 골랐다. 이제 그 환경변수는 유료를
        # 고르지 못한다 - 고르지 않은 사람이 요금을 무는 길이었기
        # 때문이다. 고르는 자리는 화면이고, 그것이 닿는 곳이 이 인자다
        # (Sprint125 가 같은 이유로 만들어 두었다).
        #
        # 이 시험이 재는 것은 그대로다: 고른 뒤에 글이 어떻게 다듬어져
        # 어느 쪽으로 가는가.
        generate_voice("텍스트", "out.mp3", provider="ElevenLabs")

        mock_elevenlabs.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_google.generate_voice.assert_not_called()

    def test_provider_explicit_google_routes_to_google(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint244 - 고른 사실을 인자로 적는다.
        #
        # 예전에는 TTS_PROVIDER 로 골랐다. 이제 그 환경변수는 유료를
        # 고르지 못한다 - 고르지 않은 사람이 요금을 무는 길이었기
        # 때문이다. 고르는 자리는 화면이고, 그것이 닿는 곳이 이 인자다
        # (Sprint125 가 같은 이유로 만들어 두었다).
        #
        # 이 시험이 재는 것은 그대로다: 고른 뒤에 글이 어떻게 다듬어져
        # 어느 쪽으로 가는가.
        generate_voice("텍스트", "out.mp3", provider="google")

        mock_google.generate_voice.assert_called_once_with("텍스트", "out.mp3")
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_an_unrecognized_value_never_falls_back_to_a_paid_provider(
        self, mock_elevenlabs, mock_google,
    ):
        """
        Sprint244 - 모르는 값이 유료로 떨어지지 않는다.

        예전에는 오타 하나가 Google 로 가는 문이었다. 모르는 이름은
        모르는 것으로 두고, 돈이 드는 쪽을 기본값으로 삼지 않는다.
        """

        from app.providers import local_voice_provider

        os.environ["TTS_PROVIDER"] = "bogus"

        with patch.object(local_voice_provider, "generate_voice",
                          return_value="out.mp3"):
            generate_voice("텍스트", "out.mp3")

        mock_google.generate_voice.assert_not_called()
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_elevenlabs_failure_never_silently_falls_back_to_google(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint244 - 고른 사실을 인자로 적는다.
        #
        # 예전에는 TTS_PROVIDER 로 골랐다. 이제 그 환경변수는 유료를
        # 고르지 못한다 - 고르지 않은 사람이 요금을 무는 길이었기
        # 때문이다. 고르는 자리는 화면이고, 그것이 닿는 곳이 이 인자다
        # (Sprint125 가 같은 이유로 만들어 두었다).
        #
        # 이 시험이 재는 것은 그대로다: 고른 뒤에 글이 어떻게 다듬어져
        # 어느 쪽으로 가는가.
        mock_elevenlabs.generate_voice.side_effect = Exception("ElevenLabs API 실패")

        with self.assertRaises(Exception):
            generate_voice("텍스트", "out.mp3", provider="elevenlabs")

        mock_google.generate_voice.assert_not_called()

    def test_elevenlabs_path_applies_voice_quality_pause_markup(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint27 Voice Quality Engine(optimize_for_tts)이 실제로
        # ElevenLabs 호출 경로에 연결되어 있는지 확인한다 - narration
        # 원문이 아니라 pause 마크업이 삽입된 텍스트가 전달돼야 한다.
        # Sprint244 - 고른 사실을 인자로 적는다.
        #
        # 예전에는 TTS_PROVIDER 로 골랐다. 이제 그 환경변수는 유료를
        # 고르지 못한다 - 고르지 않은 사람이 요금을 무는 길이었기
        # 때문이다. 고르는 자리는 화면이고, 그것이 닿는 곳이 이 인자다
        # (Sprint125 가 같은 이유로 만들어 두었다).
        #
        # 이 시험이 재는 것은 그대로다: 고른 뒤에 글이 어떻게 다듬어져
        # 어느 쪽으로 가는가.
        generate_voice("좋은 아침입니다. 시작해볼까요?", "out.mp3",
                       provider="elevenlabs")

        called_text = mock_elevenlabs.generate_voice.call_args[0][0]

        self.assertIn('<break time="0.4s" />', called_text)
        self.assertNotEqual(called_text, "좋은 아침입니다. 시작해볼까요?")
        mock_google.generate_voice.assert_not_called()

    def test_google_path_never_receives_pause_markup(
        self, mock_elevenlabs, mock_google,
    ):
        # Google TTS는 <break> 마크업을 해석하지 않고 그대로 읽어버리므로
        # (SynthesisInput(text=...)), 이 마크업이 절대 섞여 들어가면 안 된다.
        # Sprint244 - 고른 사실을 인자로 적는다.
        #
        # 예전에는 TTS_PROVIDER 로 골랐다. 이제 그 환경변수는 유료를
        # 고르지 못한다 - 고르지 않은 사람이 요금을 무는 길이었기
        # 때문이다. 고르는 자리는 화면이고, 그것이 닿는 곳이 이 인자다
        # (Sprint125 가 같은 이유로 만들어 두었다).
        #
        # 이 시험이 재는 것은 그대로다: 고른 뒤에 글이 어떻게 다듬어져
        # 어느 쪽으로 가는가.
        generate_voice("좋은 아침입니다. 시작해볼까요?", "out.mp3",
                       provider="google")

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
        # Sprint244 - 고른 사실을 인자로 적는다.
        #
        # 예전에는 TTS_PROVIDER 로 골랐다. 이제 그 환경변수는 유료를
        # 고르지 못한다 - 고르지 않은 사람이 요금을 무는 길이었기
        # 때문이다. 고르는 자리는 화면이고, 그것이 닿는 곳이 이 인자다
        # (Sprint125 가 같은 이유로 만들어 두었다).
        #
        # 이 시험이 재는 것은 그대로다: 고른 뒤에 글이 어떻게 다듬어져
        # 어느 쪽으로 가는가.
        generate_voice("밤에 2번 이상 화장실 가세요?", "out.mp3",
                       provider="google")

        mock_google.generate_voice.assert_called_once_with(
            "밤에 두 번 이상 화장실 가세요?", "out.mp3",
        )
        mock_elevenlabs.generate_voice.assert_not_called()

    def test_elevenlabs_path_does_not_apply_speech_normalization(
        self, mock_elevenlabs, mock_google,
    ):
        # Sprint52 범위는 "Google TTS 입력 텍스트만" - ElevenLabs
        # 경로는 이 스프린트에서 건드리지 않는다.
        # Sprint244 - 고른 사실을 인자로 적는다.
        #
        # 예전에는 TTS_PROVIDER 로 골랐다. 이제 그 환경변수는 유료를
        # 고르지 못한다 - 고르지 않은 사람이 요금을 무는 길이었기
        # 때문이다. 고르는 자리는 화면이고, 그것이 닿는 곳이 이 인자다
        # (Sprint125 가 같은 이유로 만들어 두었다).
        #
        # 이 시험이 재는 것은 그대로다: 고른 뒤에 글이 어떻게 다듬어져
        # 어느 쪽으로 가는가.
        generate_voice("2번", "out.mp3", provider="elevenlabs")

        called_text = mock_elevenlabs.generate_voice.call_args[0][0]
        self.assertIn("2번", called_text)
        self.assertNotIn("두 번", called_text)


if __name__ == "__main__":
    unittest.main()
