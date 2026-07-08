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

from app.services.duration_optimizer import (
    MIN_ACCEPTABLE_SECONDS,
    MAX_ACCEPTABLE_SECONDS,
    MIN_SPEAKING_RATE,
    MAX_SPEAKING_RATE,
    MAX_PAUSE_SECONDS,
    TARGET_DURATION_SECONDS,
    get_audio_duration,
    append_silence,
    speed_up_audio,
    optimize_scene_audio,
)


class TestGetAudioDuration(unittest.TestCase):

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_parses_ffprobe_stdout(self, mock_run):
        mock_run.return_value = MagicMock(stdout="7.569705\n", stderr="")
        self.assertAlmostEqual(get_audio_duration("scene1.mp3"), 7.569705, places=5)

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_empty_stdout_returns_zero(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        self.assertEqual(get_audio_duration("missing.mp3"), 0.0)

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_uses_ffprobe_command(self, mock_run):
        mock_run.return_value = MagicMock(stdout="1.0", stderr="")
        get_audio_duration("scene1.mp3")

        command = mock_run.call_args[0][0]
        self.assertIn("ffprobe", command)
        self.assertIn("scene1.mp3", command)


class TestAppendSilenceCommand(unittest.TestCase):

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_uses_anullsrc_with_clamped_duration(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        append_silence("scene6.mp3", 1.5, "scene6.out.mp3")

        command = mock_run.call_args[0][0]
        t_index = command.index("-t")
        self.assertEqual(command[t_index + 1], "1.50")
        self.assertIn("anullsrc=r=44100:cl=mono", command)
        self.assertIn("scene6.out.mp3", command)

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_pause_seconds_is_clamped_to_max(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        append_silence("scene6.mp3", 999.0, "scene6.out.mp3")

        command = mock_run.call_args[0][0]
        t_index = command.index("-t")
        self.assertEqual(command[t_index + 1], f"{MAX_PAUSE_SECONDS:.2f}")

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_negative_pause_is_clamped_to_zero(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        append_silence("scene6.mp3", -5.0, "scene6.out.mp3")

        command = mock_run.call_args[0][0]
        t_index = command.index("-t")
        self.assertEqual(command[t_index + 1], "0.00")

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_raises_on_ffmpeg_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        with self.assertRaises(Exception):
            append_silence("scene6.mp3", 1.0, "scene6.out.mp3")


class TestSpeedUpAudioCommand(unittest.TestCase):

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_uses_atempo_filter(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        speed_up_audio("scene6.mp3", 1.03, "scene6.out.mp3")

        command = mock_run.call_args[0][0]
        filter_index = command.index("-filter:a")
        self.assertEqual(command[filter_index + 1], "atempo=1.0300")

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_rate_above_max_is_clamped(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        speed_up_audio("scene6.mp3", 2.0, "scene6.out.mp3")

        command = mock_run.call_args[0][0]
        filter_index = command.index("-filter:a")
        self.assertEqual(command[filter_index + 1], f"atempo={MAX_SPEAKING_RATE:.4f}")

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_rate_below_min_is_clamped(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        speed_up_audio("scene6.mp3", 0.5, "scene6.out.mp3")

        command = mock_run.call_args[0][0]
        filter_index = command.index("-filter:a")
        self.assertEqual(command[filter_index + 1], f"atempo={MIN_SPEAKING_RATE:.4f}")

    @patch("app.services.duration_optimizer.subprocess.run")
    def test_raises_on_ffmpeg_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

        with self.assertRaises(Exception):
            speed_up_audio("scene6.mp3", 1.03, "scene6.out.mp3")


class RealAudioTestCase(unittest.TestCase):
    """실제 ffmpeg로 짧은 무음 mp3 fixture를 만들어 진짜 파일에 대해
    검증하는 통합 테스트 베이스. ffmpeg/ffprobe는 이 프로젝트의 필수
    런타임 의존성(audio_service.py 등)이라 mocking 없이 그대로 쓴다."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_silence(self, filename: str, seconds: float) -> str:
        path = os.path.join(self.tmp_dir, filename)
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-t", f"{seconds:.2f}", "-i", "anullsrc=r=44100:cl=mono",
                "-c:a", "libmp3lame", path,
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return path


class TestGetAudioDurationReal(RealAudioTestCase):

    def test_measures_real_generated_clip(self):
        path = self._make_silence("clip.mp3", 3.0)
        self.assertAlmostEqual(get_audio_duration(path), 3.0, delta=0.1)


class TestAppendSilenceReal(RealAudioTestCase):

    def test_output_duration_is_original_plus_pause(self):
        original = self._make_silence("scene.mp3", 5.0)
        output = os.path.join(self.tmp_dir, "scene.out.mp3")

        append_silence(original, 1.5, output)

        self.assertAlmostEqual(get_audio_duration(output), 6.5, delta=0.15)

    def test_pause_longer_than_cap_is_clamped_in_real_output(self):
        original = self._make_silence("scene.mp3", 5.0)
        output = os.path.join(self.tmp_dir, "scene.out.mp3")

        append_silence(original, 999.0, output)

        self.assertAlmostEqual(
            get_audio_duration(output),
            5.0 + MAX_PAUSE_SECONDS,
            delta=0.15,
        )


class TestSpeedUpAudioReal(RealAudioTestCase):

    def test_output_duration_is_shortened_by_rate(self):
        original = self._make_silence("scene.mp3", 10.0)
        output = os.path.join(self.tmp_dir, "scene.out.mp3")

        speed_up_audio(original, 1.03, output)

        self.assertAlmostEqual(get_audio_duration(output), 10.0 / 1.03, delta=0.2)


class TestOptimizeSceneAudioReal(RealAudioTestCase):

    def test_in_range_total_leaves_files_untouched(self):
        paths = [
            self._make_silence(f"scene{i}.mp3", 7.5)
            for i in range(1, 7)
        ]  # 45.0s total
        original_durations = [get_audio_duration(p) for p in paths]

        result = optimize_scene_audio(paths)

        self.assertEqual(result["action"], "none")
        for path, original in zip(paths, original_durations):
            self.assertAlmostEqual(get_audio_duration(path), original, delta=0.05)

    def test_under_43_appends_silence_to_last_scene_only(self):
        # 6 * 6.0 = 36.0s -> 45초에 9초 부족하지만 MAX_PAUSE_SECONDS(3초)로 clamp
        paths = [self._make_silence(f"scene{i}.mp3", 6.0) for i in range(1, 7)]
        earlier_durations = [get_audio_duration(p) for p in paths[:-1]]

        result = optimize_scene_audio(paths)

        self.assertEqual(result["action"], "expand")
        for path, original in zip(paths[:-1], earlier_durations):
            self.assertAlmostEqual(get_audio_duration(path), original, delta=0.05)

        self.assertAlmostEqual(
            get_audio_duration(paths[-1]),
            6.0 + MAX_PAUSE_SECONDS,
            delta=0.15,
        )

    def test_over_47_speeds_up_last_scene_only(self):
        # 6 * 9.0 = 54.0s -> 47초 초과
        paths = [self._make_silence(f"scene{i}.mp3", 9.0) for i in range(1, 7)]
        earlier_durations = [get_audio_duration(p) for p in paths[:-1]]

        result = optimize_scene_audio(paths)

        self.assertEqual(result["action"], "contract")
        for path, original in zip(paths[:-1], earlier_durations):
            self.assertAlmostEqual(get_audio_duration(path), original, delta=0.05)

        new_last = get_audio_duration(paths[-1])
        self.assertLess(new_last, 9.0)
        self.assertAlmostEqual(new_last, 9.0 / MAX_SPEAKING_RATE, delta=0.2)

    def test_empty_list_returns_none_action(self):
        result = optimize_scene_audio([])
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["original_total"], 0.0)


if __name__ == "__main__":
    unittest.main()
