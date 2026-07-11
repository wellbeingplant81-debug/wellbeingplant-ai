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
        # 6 * 6.9 = 41.4s -> 45초에 3.6초 부족하지만 MAX_PAUSE_SECONDS(3초)로
        # clamp해도 41.4+3.0=44.4로 43~47 범위에 들어오는 "보통" 케이스.
        # last scene 단독 보정만으로 충분하므로 2차 보정(cascade)은 발동되지 않아야 한다.
        paths = [self._make_silence(f"scene{i}.mp3", 6.9) for i in range(1, 7)]
        earlier_durations = [get_audio_duration(p) for p in paths[:-1]]

        result = optimize_scene_audio(paths)

        self.assertEqual(result["action"], "expand")
        self.assertFalse(result.get("secondary_adjustment", False))
        for path, original in zip(paths[:-1], earlier_durations):
            self.assertAlmostEqual(get_audio_duration(path), original, delta=0.05)

        self.assertAlmostEqual(
            get_audio_duration(paths[-1]),
            6.9 + MAX_PAUSE_SECONDS,
            delta=0.15,
        )
        self.assertGreaterEqual(result["final_total"], MIN_ACCEPTABLE_SECONDS)
        self.assertLessEqual(result["final_total"], MAX_ACCEPTABLE_SECONDS)

    def test_over_47_speeds_up_last_scene_only(self):
        # 6 * 7.85 = 47.1s -> 47초를 살짝 초과하지만 last scene 단독의 최대
        # 압축(±3%)만으로도 46.87s까지 내려가 43~47 범위에 들어오는 "보통" 케이스.
        # 2차 보정(cascade)은 발동되지 않아야 한다.
        paths = [self._make_silence(f"scene{i}.mp3", 7.85) for i in range(1, 7)]
        earlier_durations = [get_audio_duration(p) for p in paths[:-1]]

        result = optimize_scene_audio(paths)

        self.assertEqual(result["action"], "contract")
        self.assertFalse(result.get("secondary_adjustment", False))
        for path, original in zip(paths[:-1], earlier_durations):
            self.assertAlmostEqual(get_audio_duration(path), original, delta=0.05)

        new_last = get_audio_duration(paths[-1])
        self.assertLess(new_last, 7.85)
        self.assertAlmostEqual(new_last, 7.85 / MAX_SPEAKING_RATE, delta=0.2)
        self.assertGreaterEqual(result["final_total"], MIN_ACCEPTABLE_SECONDS)
        self.assertLessEqual(result["final_total"], MAX_ACCEPTABLE_SECONDS)

    def test_severely_under_43_falls_back_to_secondary_scene_adjustment(self):
        # 6 * 6.076 = 36.456s -> 2026-07-10 실제 E2E 실패 케이스 재현.
        # last scene 단독 무음 패딩(3초 cap)만으로는 39.456s로 여전히 43초
        # 미만이라, 나머지 scene에도 MIN_SPEAKING_RATE(감속)를 추가로 적용해
        # 최대한 43초에 가깝게 만들어야 한다(완전히 범위 안에 들어오지
        # 않을 수 있는 극단적 케이스지만, 반드시 개선은 되어야 한다).
        paths = [self._make_silence(f"scene{i}.mp3", 6.076) for i in range(1, 7)]
        earlier_durations = [get_audio_duration(p) for p in paths[:-1]]

        result = optimize_scene_audio(paths)

        self.assertEqual(result["action"], "expand")
        self.assertTrue(result.get("secondary_adjustment", False))

        pad_only_total = 6.076 + MAX_PAUSE_SECONDS
        pad_only_final_total = 6.076 * 5 + pad_only_total

        self.assertGreater(result["final_total"], pad_only_final_total)

        for path, original in zip(paths[:-1], earlier_durations):
            self.assertGreater(get_audio_duration(path), original)
            self.assertAlmostEqual(
                get_audio_duration(path),
                original / MIN_SPEAKING_RATE,
                delta=0.1,
            )

    def test_severely_over_47_falls_back_to_secondary_scene_adjustment(self):
        # 6 * 8.044 = 48.264s -> 2026-07-10 실제 E2E 실패 케이스 재현.
        # last scene 단독 압축(±3% cap)만으로는 48.03s로 여전히 47초를
        # 초과하므로, 나머지 scene에도 MAX_SPEAKING_RATE(가속)를 추가로
        # 적용해 43~47초 범위 안으로 들어와야 한다.
        paths = [self._make_silence(f"scene{i}.mp3", 8.044) for i in range(1, 7)]
        earlier_durations = [get_audio_duration(p) for p in paths[:-1]]

        result = optimize_scene_audio(paths)

        self.assertEqual(result["action"], "contract")
        self.assertTrue(result.get("secondary_adjustment", False))

        for path, original in zip(paths[:-1], earlier_durations):
            self.assertLess(get_audio_duration(path), original)
            self.assertAlmostEqual(
                get_audio_duration(path),
                original / MAX_SPEAKING_RATE,
                delta=0.1,
            )

        self.assertGreaterEqual(result["final_total"], MIN_ACCEPTABLE_SECONDS)
        self.assertLessEqual(result["final_total"], MAX_ACCEPTABLE_SECONDS)

    def test_empty_list_returns_none_action(self):
        result = optimize_scene_audio([])
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["original_total"], 0.0)


if __name__ == "__main__":
    unittest.main()
