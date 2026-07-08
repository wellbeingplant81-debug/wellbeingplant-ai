import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.audio_service import (
    mix_audio,
    NARRATION_VOLUME_DB,
    BGM_VOLUME_DB,
    BGM_FADE_IN_SECONDS,
    BGM_FADE_OUT_SECONDS,
)
from app.services.duration_optimizer import get_audio_duration


class TestMixAudioCommand(unittest.TestCase):
    """ffmpeg 명령 조립 자체를 mock으로 빠르게 검증 (final_video_service
    테스트와 동일한 프로젝트 관례)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp_dir, "audio"))
        with open(os.path.join(self.tmp_dir, "audio", "voice.mp3"), "wb") as f:
            f.write(b"fake voice")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("app.services.audio_service.select_bgm", return_value="fake_bgm.mp3")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.subprocess.run")
    def test_volumes_are_the_defined_constants(self, mock_run, mock_duration, mock_select):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mix_audio(self.tmp_dir)

        command = mock_run.call_args[0][0]
        filter_complex = command[command.index("-filter_complex") + 1]

        self.assertIn(f"volume={BGM_VOLUME_DB}dB", filter_complex)
        self.assertIn(f"volume={NARRATION_VOLUME_DB}dB", filter_complex)

    @patch("app.services.audio_service.select_bgm", return_value="fake_bgm.mp3")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.subprocess.run")
    def test_fade_in_and_out_durations(self, mock_run, mock_duration, mock_select):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mix_audio(self.tmp_dir)

        filter_complex = mock_run.call_args[0][0][
            mock_run.call_args[0][0].index("-filter_complex") + 1
        ]

        self.assertIn(f"afade=t=in:st=0:d={BGM_FADE_IN_SECONDS}", filter_complex)
        self.assertIn(f"d={BGM_FADE_OUT_SECONDS}", filter_complex)

    @patch("app.services.audio_service.select_bgm", return_value="fake_bgm.mp3")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.subprocess.run")
    def test_fade_out_start_is_based_on_real_voice_duration(
        self, mock_run, mock_duration, mock_select
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mix_audio(self.tmp_dir)

        filter_complex = mock_run.call_args[0][0][
            mock_run.call_args[0][0].index("-filter_complex") + 1
        ]
        expected_start = 45.0 - BGM_FADE_OUT_SECONDS

        self.assertIn(f"afade=t=out:st={expected_start:.3f}", filter_complex)

    @patch("app.services.audio_service.select_bgm", return_value="fake_bgm.mp3")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.subprocess.run")
    def test_bgm_category_is_forwarded_to_select_bgm(
        self, mock_run, mock_duration, mock_select
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mix_audio(self.tmp_dir, bgm_category="calm")

        mock_select.assert_called_once_with("calm")

    @patch("app.services.audio_service.select_bgm", return_value="fake_bgm.mp3")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.subprocess.run")
    def test_bgm_input_uses_infinite_loop(self, mock_run, mock_duration, mock_select):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mix_audio(self.tmp_dir)

        command = mock_run.call_args[0][0]
        self.assertIn("-stream_loop", command)
        self.assertEqual(command[command.index("-stream_loop") + 1], "-1")

    @patch("app.services.audio_service.select_bgm", return_value="fake_bgm.mp3")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.subprocess.run")
    def test_raises_on_ffmpeg_failure(self, mock_run, mock_duration, mock_select):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        with self.assertRaises(Exception):
            mix_audio(self.tmp_dir)


class RealAudioMixTestCase(unittest.TestCase):
    """실제 ffmpeg로 짧은 무음 mp3 fixture를 만들어 진짜 믹싱 결과를
    검증하는 통합 테스트 베이스."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_path = os.path.join(self.tmp_dir, "project")
        os.makedirs(os.path.join(self.project_path, "audio"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_tone(self, path: str, seconds: float, freq: int = 440):
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-t", f"{seconds:.2f}",
                "-i", f"sine=frequency={freq}:sample_rate=44100",
                "-c:a", "libmp3lame", path,
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return path

    def _make_voice(self, seconds: float) -> str:
        path = os.path.join(self.project_path, "audio", "voice.mp3")
        return self._make_tone(path, seconds, freq=440)

    def _mean_volume_db(self, path: str) -> float:
        return self._volumedetect(path, "mean_volume")

    def _max_volume_db(self, path: str) -> float:
        return self._volumedetect(path, "max_volume")

    def _volumedetect(self, path: str, key: str) -> float:
        result = subprocess.run(
            ["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        for line in result.stderr.splitlines():
            if key in line:
                return float(line.split(":")[1].strip().split(" ")[0])
        raise AssertionError(f"{key} not found in ffmpeg output: {result.stderr}")


class TestLoopShortBgm(RealAudioMixTestCase):

    def test_short_bgm_is_looped_to_cover_full_voice_length(self):
        voice_path = self._make_voice(10.0)
        bgm_path = os.path.join(self.tmp_dir, "short_bgm.mp3")
        self._make_tone(bgm_path, 3.0, freq=880)

        with patch("app.services.audio_service.select_bgm", return_value=bgm_path):
            mix_audio(self.project_path)

        output = os.path.join(self.project_path, "audio", "final_audio.mp3")
        self.assertAlmostEqual(get_audio_duration(output), 10.0, delta=0.15)


class TestTrimLongBgm(RealAudioMixTestCase):

    def test_long_bgm_is_trimmed_to_voice_length(self):
        voice_path = self._make_voice(5.0)
        bgm_path = os.path.join(self.tmp_dir, "long_bgm.mp3")
        self._make_tone(bgm_path, 20.0, freq=880)

        with patch("app.services.audio_service.select_bgm", return_value=bgm_path):
            mix_audio(self.project_path)

        output = os.path.join(self.project_path, "audio", "final_audio.mp3")
        self.assertAlmostEqual(get_audio_duration(output), 5.0, delta=0.15)


class TestNarrationNotAttenuatedByMix(RealAudioMixTestCase):
    """amix의 기본 normalize=1은 스트림 수로 나눠(2개 입력이면 -6dB)
    narration까지 조용히 줄여버린다 - "음성이 항상 최우선"이라는
    Sprint54 원칙과 NARRATION_VOLUME_DB=0의 의미가 깨진다. 실측으로
    회귀를 잠근다."""

    def test_narration_peak_volume_is_not_attenuated_by_bgm_mix(self):
        voice_path = self._make_voice(6.0)
        bgm_path = os.path.join(self.tmp_dir, "bgm.mp3")
        self._make_tone(bgm_path, 6.0, freq=880)

        voice_alone_max_db = self._max_volume_db(voice_path)

        with patch("app.services.audio_service.select_bgm", return_value=bgm_path):
            mix_audio(self.project_path)

        output = os.path.join(self.project_path, "audio", "final_audio.mp3")
        mix_max_db = self._max_volume_db(output)

        # amix normalize=1이면 약 -6dB 떨어진다 - 1dB 이내로 유지되어야
        # narration이 실질적으로 그대로 유지된 것이다.
        self.assertAlmostEqual(mix_max_db, voice_alone_max_db, delta=1.0)


class TestMergeContainsBgm(RealAudioMixTestCase):

    def test_final_mix_audio_differs_from_voice_alone(self):
        # BGM이 실제로 섞여 들어갔다면, voice 단독보다 최종 결과물의
        # 평균 음량(mean_volume)이 달라야 한다 (침묵 narration + 낮은
        # 볼륨의 BGM만 섞어서, BGM 유무 자체가 신호로 드러나게 한다).
        voice_path = os.path.join(self.project_path, "audio", "voice.mp3")
        # 무음 narration - BGM이 섞이지 않으면 최종 결과도 완전 무음이어야 한다.
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-t", "6.0",
                "-i", "anullsrc=r=44100:cl=mono",
                "-c:a", "libmp3lame", voice_path,
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        bgm_path = os.path.join(self.tmp_dir, "bgm.mp3")
        self._make_tone(bgm_path, 6.0, freq=880)

        with patch("app.services.audio_service.select_bgm", return_value=bgm_path):
            mix_audio(self.project_path)

        output = os.path.join(self.project_path, "audio", "final_audio.mp3")

        voice_alone_db = self._mean_volume_db(voice_path)
        final_mix_db = self._mean_volume_db(output)

        # 무음(-91dB 근방)이었던 narration에 BGM이 섞였다면 최종 결과는
        # 훨씬 더 커야 한다(무음이 아니게 된다).
        self.assertGreater(final_mix_db, voice_alone_db + 20)


if __name__ == "__main__":
    unittest.main()
