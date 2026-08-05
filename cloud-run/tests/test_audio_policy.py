"""
Sprint63 - Master Quality Audio.

나레이션 오디오가 최종 MP4에 닿기까지 몇 번 손실 인코딩되는지를
고정하는 계약 테스트다. Sprint62까지는 5회(그중 4회가 32kbps)였다:

  Google TTS(MP3 32kbps) -> Duration Optimizer(libmp3lame 32kbps)
  -> concat(libmp3lame 32kbps) -> mix(mp3 32kbps) -> AAC

이 테스트들은 그 체인이 "무손실 PCM 구간 + 최종 AAC 1회"로 유지되는지
검사한다. 실측 근거(2026-08-05, ko-KR-Chirp3-HD-Aoede, 동일 문장):

  MP3          99.9% rolloff 5,848Hz
  LINEAR16     99.9% rolloff 9,152Hz
  LINEAR16 48k 99.9% rolloff 7,746Hz, E(>11kHz) 0.002% -> 업샘플링일 뿐
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import audio_policy


class TestAudioPolicyConstants(unittest.TestCase):

    def test_narration_stays_at_chirp3_native_sample_rate(self):
        # 48000을 요청해도 Chirp3-HD의 실제 대역은 늘지 않는다 - 바이트만
        # 두 배가 된다. 네이티브 24kHz를 그대로 쓴다.
        self.assertEqual(audio_policy.NARRATION_SAMPLE_RATE_HZ, 24000)

    def test_narration_is_mono(self):
        self.assertEqual(audio_policy.NARRATION_CHANNELS, 1)

    def test_intermediate_format_is_lossless_pcm(self):
        self.assertEqual(audio_policy.NARRATION_EXTENSION, ".wav")
        self.assertEqual(audio_policy.NARRATION_PCM_CODEC, "pcm_s16le")

    def test_delivery_codec_keeps_mp4_compatibility(self):
        self.assertEqual(audio_policy.DELIVERY_AUDIO_CODEC, "aac")
        self.assertEqual(audio_policy.DELIVERY_AUDIO_BITRATE, "192k")

    def test_filenames_derive_from_the_single_extension(self):
        ext = audio_policy.NARRATION_EXTENSION

        self.assertEqual(audio_policy.VOICE_FILENAME, f"voice{ext}")
        self.assertEqual(audio_policy.FINAL_AUDIO_FILENAME, f"final_audio{ext}")
        self.assertEqual(audio_policy.scene_audio_filename(3), f"scene3{ext}")

    def test_scene_audio_glob_matches_the_scene_filenames(self):
        import fnmatch

        self.assertTrue(
            fnmatch.fnmatch(
                audio_policy.scene_audio_filename(7),
                audio_policy.SCENE_AUDIO_GLOB,
            )
        )


class TestGoogleTtsRequestsLossless(unittest.TestCase):

    @patch("app.providers.google_tts_provider.texttospeech")
    def test_requests_linear16_at_policy_sample_rate(self, mock_tts):
        from app.providers import google_tts_provider

        mock_tts.AudioEncoding.LINEAR16 = "LINEAR16"

        client = MagicMock()
        client.synthesize_speech.return_value = MagicMock(audio_content=b"x")
        mock_tts.TextToSpeechClient.return_value = client

        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            google_tts_provider.generate_voice(
                "안녕하세요", os.path.join(tmp_dir, "audio", "scene1.wav"),
            )

        config_kwargs = mock_tts.AudioConfig.call_args.kwargs

        self.assertEqual(config_kwargs["audio_encoding"], "LINEAR16")
        self.assertEqual(
            config_kwargs["sample_rate_hertz"],
            audio_policy.NARRATION_SAMPLE_RATE_HZ,
        )


class TestNoLossyReencodeInTheChain(unittest.TestCase):
    """중간 단계 어디에서도 손실 코덱을 쓰지 않는지 확인한다."""

    LOSSY = ("libmp3lame", "mp3", "libvorbis", "libopus")

    @patch("app.services.audio_service.subprocess.run")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.select_bgm", return_value="bgm.mp3")
    def test_mix_audio_writes_lossless_pcm(self, _bgm, _dur, mock_run):
        from app.services import audio_service

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        audio_service.mix_audio("output/proj")

        command = mock_run.call_args[0][0]

        self.assertIn(audio_policy.NARRATION_PCM_CODEC, command)
        for codec in self.LOSSY:
            self.assertNotIn(codec, command)

    @patch("app.services.audio_service.subprocess.run")
    def test_concat_writes_lossless_pcm(self, mock_run):
        from app.services import audio_service

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_service.concat_scene_audio(
                [os.path.join(tmp_dir, "scene1.wav")],
                os.path.join(tmp_dir, "voice.wav"),
            )

        command = mock_run.call_args[0][0]

        self.assertIn(audio_policy.NARRATION_PCM_CODEC, command)
        for codec in self.LOSSY:
            self.assertNotIn(codec, command)

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_append_silence_writes_lossless_pcm_at_policy_rate(self, mock_run):
        from app.services import duration_optimizer

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        duration_optimizer.append_silence("in.wav", 1.5, "out.wav")

        command = mock_run.call_args[0][0]

        self.assertIn(audio_policy.NARRATION_PCM_CODEC, command)
        self.assertNotIn("libmp3lame", command)

        # 무음 소스 샘플레이트가 나레이션과 다르면 concat 필터가 전체를
        # 리샘플한다 - 정책 샘플레이트로 맞춘다.
        anullsrc = [arg for arg in command if "anullsrc" in str(arg)]
        self.assertTrue(anullsrc)
        self.assertIn(
            f"r={audio_policy.NARRATION_SAMPLE_RATE_HZ}", anullsrc[0],
        )

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_speed_up_writes_lossless_pcm(self, mock_run):
        from app.services import duration_optimizer

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        duration_optimizer.speed_up_audio("in.wav", 1.02, "out.wav")

        command = mock_run.call_args[0][0]

        self.assertIn(audio_policy.NARRATION_PCM_CODEC, command)
        self.assertNotIn("libmp3lame", command)


class TestDeliveryContract(unittest.TestCase):
    """최종 MP4는 여전히 H.264 + AAC여야 한다 (MP4 호환성 유지)."""

    @patch("app.services.final_video_service.subprocess.run")
    def test_final_mux_reads_policy_audio_and_writes_aac(self, mock_run):
        from app.services.final_video_service import merge_video_audio

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        merge_video_audio("output/proj")

        command = mock_run.call_args[0][0]

        self.assertIn(audio_policy.DELIVERY_AUDIO_CODEC, command)
        self.assertIn(audio_policy.DELIVERY_AUDIO_BITRATE, command)

        audio_input = [
            arg for arg in command
            if str(arg).endswith(audio_policy.FINAL_AUDIO_FILENAME)
        ]
        self.assertTrue(
            audio_input,
            "최종 mux가 정책 오디오 파일명을 읽어야 한다",
        )


if __name__ == "__main__":
    unittest.main()
