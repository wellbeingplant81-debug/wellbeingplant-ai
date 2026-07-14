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
    DUCK_THRESHOLD,
    DUCK_RATIO,
    DUCK_ATTACK_MS,
    DUCK_RELEASE_MS,
    DUCK_MAKEUP,
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

    @patch("app.services.audio_service.select_bgm", return_value="fake_bgm.mp3")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.subprocess.run")
    def test_sidechaincompress_uses_duck_constants(self, mock_run, mock_duration, mock_select):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mix_audio(self.tmp_dir)

        filter_complex = mock_run.call_args[0][0][
            mock_run.call_args[0][0].index("-filter_complex") + 1
        ]

        self.assertIn("sidechaincompress=", filter_complex)
        self.assertIn(f"threshold={DUCK_THRESHOLD}", filter_complex)
        self.assertIn(f"ratio={DUCK_RATIO}", filter_complex)
        self.assertIn(f"attack={DUCK_ATTACK_MS}", filter_complex)
        self.assertIn(f"release={DUCK_RELEASE_MS}", filter_complex)
        self.assertIn(f"makeup={DUCK_MAKEUP}", filter_complex)

    @patch("app.services.audio_service.select_bgm", return_value="fake_bgm.mp3")
    @patch("app.services.audio_service.get_audio_duration", return_value=45.0)
    @patch("app.services.audio_service.subprocess.run")
    def test_narration_is_the_sidechain_control_signal(self, mock_run, mock_duration, mock_select):
        # sidechaincompress의 두 번째 입력(사이드체인)이 narration([voice])
        # 이어야 한다 - narration이 클 때 BGM([bgm])이 눌리는 구조.
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mix_audio(self.tmp_dir)

        filter_complex = mock_run.call_args[0][0][
            mock_run.call_args[0][0].index("-filter_complex") + 1
        ]

        self.assertIn("[bgm][voice]sidechaincompress", filter_complex)


class TestBgmVolumeSprint97Reduction(unittest.TestCase):
    """Sprint97 - narration 전달력 우선을 위해 BGM 볼륨을 기존(-28.0dB)
    대비 약 10% 낮췄다(-30.8dB). Sprint100-4가 그 값을 다시 낮췄으므로
    (아래 TestBgmVolumeSprint100_4Reduction), 이 테스트는 그 중간
    단계(-30.8dB)가 실제로 -28.0dB보다 낮다는 방향성만 고정한다."""

    def test_bgm_volume_is_lower_than_sprint97_baseline(self):
        PRE_SPRINT97_BGM_VOLUME_DB = -28.0
        self.assertLess(BGM_VOLUME_DB, PRE_SPRINT97_BGM_VOLUME_DB)


class TestBgmVolumeSprint100_4Reduction(unittest.TestCase):
    """Sprint100-4 - Production QA에서 BGM이 여전히 narration을 살짝
    가린다는 피드백으로 Sprint97의 -30.8dB에서 -34.0dB로 추가
    하향한다(gain 값만 조정, 믹싱 구조는 그대로 유지)."""

    def test_bgm_volume_is_negative_34_db(self):
        self.assertAlmostEqual(BGM_VOLUME_DB, -34.0, places=1)

    def test_bgm_volume_is_lower_than_sprint97_value(self):
        SPRINT97_BGM_VOLUME_DB = -30.8
        self.assertLess(BGM_VOLUME_DB, SPRINT97_BGM_VOLUME_DB)


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


class TestBgmDucking(RealAudioMixTestCase):
    """Sprint54-2 - sidechaincompress 기반 ducking. narration이 나오는
    동안 BGM이 확실히 줄고, narration이 끝나면 release 시간 안에
    원래(ducking 없는 BGM_VOLUME_DB 기준) 볼륨으로 자연스럽게
    복귀해야 한다."""

    def _make_voice_then_silence(self, loud_seconds: float, silence_seconds: float) -> str:
        # 처음 loud_seconds는 narration 실측 피크(-1.5dB 근방)에 가깝게
        # 키운 톤, 이어서 silence_seconds는 완전 무음 - 실제 narration의
        # "말하는 구간 -> 조용한 구간" 전환을 흉내낸다.
        path = os.path.join(self.project_path, "audio", "voice.mp3")
        loud_path = os.path.join(self.tmp_dir, "_loud.mp3")
        silence_path = os.path.join(self.tmp_dir, "_silence.mp3")

        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{loud_seconds:.2f}",
             "-i", "sine=frequency=440:sample_rate=44100",
             "-af", "volume=18dB", "-c:a", "libmp3lame", loud_path],
            capture_output=True, text=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{silence_seconds:.2f}",
             "-i", "anullsrc=r=44100:cl=mono",
             "-c:a", "libmp3lame", silence_path],
            capture_output=True, text=True,
        )
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", loud_path, "-i", silence_path,
             "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
             "-map", "[out]", "-c:a", "libmp3lame", path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return path

    def test_bgm_is_ducked_while_narration_plays(self):
        self._make_voice_then_silence(loud_seconds=4.0, silence_seconds=4.0)
        bgm_path = os.path.join(self.tmp_dir, "bgm.mp3")
        self._make_tone(bgm_path, 8.0, freq=880)

        # ducking이 전혀 없을 때(BGM_VOLUME_DB 고정)의 BGM 기준 음량
        baseline_db = self._mean_volume_db_of_filtered(bgm_path, f"volume={BGM_VOLUME_DB}dB")

        with patch("app.services.audio_service.select_bgm", return_value=bgm_path):
            mix_audio(self.project_path)

        output = os.path.join(self.project_path, "audio", "final_audio.mp3")

        # narration이 확실히 재생 중인 구간(초반 여유를 두고 1.0~3.0s)의
        # 최종 믹스 음량은, BGM만 있을 때보다 narration(0dB, 훨씬 큼)이
        # 지배적이라 오히려 커 보일 수 있으므로, 대신 BGM 트랙 자체가
        # 얼마나 눌렸는지 별도로 분리해서 측정한다.
        during_db = self._duck_only_mean_db(bgm_path, self.project_path, window=(1.0, 2.0))

        self.assertLess(during_db, baseline_db - 5.0)

    def test_bgm_recovers_after_narration_ends(self):
        self._make_voice_then_silence(loud_seconds=3.0, silence_seconds=5.0)
        bgm_path = os.path.join(self.tmp_dir, "bgm.mp3")
        self._make_tone(bgm_path, 8.0, freq=880)

        baseline_db = self._mean_volume_db_of_filtered(bgm_path, f"volume={BGM_VOLUME_DB}dB")

        with patch("app.services.audio_service.select_bgm", return_value=bgm_path):
            mix_audio(self.project_path)

        # narration이 끝난(3.0s) 지 release(0.4s)보다 충분히 지난 뒤(5.0~6.5s)
        # BGM만 분리해서 측정하면 BGM_VOLUME_DB 기준과 가까워야 한다.
        recovered_db = self._duck_only_mean_db(bgm_path, self.project_path, window=(5.0, 6.5))

        self.assertAlmostEqual(recovered_db, baseline_db, delta=3.0)

    def _duck_only_mean_db(self, bgm_path, project_path, window):
        """실제 mix_audio()가 만든 것과 동일한 sidechaincompress 체인을
        BGM 단독 출력으로 다시 만들어(narration과 섞지 않고) 그 구간의
        음량만 측정한다 - narration 자체의 큰 음량에 가려지지 않게
        BGM만의 ducking 정도를 직접 확인하기 위함이다."""

        from app.services.audio_service import (
            BGM_VOLUME_DB, BGM_FADE_IN_SECONDS, BGM_FADE_OUT_SECONDS,
            NARRATION_VOLUME_DB, DUCK_THRESHOLD, DUCK_RATIO, DUCK_ATTACK_MS,
            DUCK_RELEASE_MS, DUCK_MAKEUP,
        )

        voice_path = os.path.join(project_path, "audio", "voice.mp3")
        duration = get_audio_duration(voice_path)
        fade_out_start = max(duration - BGM_FADE_OUT_SECONDS, 0.0)
        isolated_path = os.path.join(self.tmp_dir, "_isolated_bgm.mp3")

        subprocess.run(
            [
                "ffmpeg", "-y", "-i", voice_path, "-stream_loop", "-1", "-i", bgm_path,
                "-filter_complex",
                (
                    f"[1:a]volume={BGM_VOLUME_DB}dB,"
                    f"afade=t=in:st=0:d={BGM_FADE_IN_SECONDS},"
                    f"afade=t=out:st={fade_out_start:.3f}:d={BGM_FADE_OUT_SECONDS}[bgm];"
                    f"[0:a]volume={NARRATION_VOLUME_DB}dB[voice];"
                    f"[bgm][voice]sidechaincompress=threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}:"
                    f"attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}:makeup={DUCK_MAKEUP}[out]"
                ),
                "-map", "[out]", "-t", f"{duration:.3f}",
                "-c:a", "libmp3lame", isolated_path,
            ],
            capture_output=True, text=True,
        )

        start, end = window
        return self._volumedetect_window(isolated_path, start, end - start, "mean_volume")

    def _mean_volume_db_of_filtered(self, path, af):
        result = subprocess.run(
            ["ffmpeg", "-i", path, "-af", f"{af},volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        for line in result.stderr.splitlines():
            if "mean_volume" in line:
                return float(line.split(":")[1].strip().split(" ")[0])
        raise AssertionError(f"mean_volume not found: {result.stderr}")

    def _volumedetect_window(self, path, start, length, key):
        result = subprocess.run(
            ["ffmpeg", "-ss", f"{start}", "-t", f"{length}", "-i", path,
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        for line in result.stderr.splitlines():
            if key in line:
                return float(line.split(":")[1].strip().split(" ")[0])
        raise AssertionError(f"{key} not found: {result.stderr}")


class TestBgmDuckingRobustness(RealAudioMixTestCase):

    def test_very_short_narration_does_not_break(self):
        voice_path = self._make_voice(0.4)
        bgm_path = os.path.join(self.tmp_dir, "bgm.mp3")
        self._make_tone(bgm_path, 10.0, freq=880)

        with patch("app.services.audio_service.select_bgm", return_value=bgm_path):
            mix_audio(self.project_path)

        output = os.path.join(self.project_path, "audio", "final_audio.mp3")
        self.assertAlmostEqual(get_audio_duration(output), 0.4, delta=0.15)

    def test_long_narration_still_works(self):
        voice_path = self._make_voice(60.0)
        bgm_path = os.path.join(self.tmp_dir, "bgm.mp3")
        self._make_tone(bgm_path, 20.0, freq=880)

        with patch("app.services.audio_service.select_bgm", return_value=bgm_path):
            mix_audio(self.project_path)

        output = os.path.join(self.project_path, "audio", "final_audio.mp3")
        self.assertAlmostEqual(get_audio_duration(output), 60.0, delta=0.3)


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
