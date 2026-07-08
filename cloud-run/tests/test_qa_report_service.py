import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.qa_report_service import (
    get_real_durations,
    load_quality_summary,
    build_qa_report,
    format_report,
)


class RealProjectFixture(unittest.TestCase):
    """실제 ffmpeg로 짧은 mp3/mp4 fixture를 만들어 진짜 project_path
    구조에 대해 검증하는 통합 테스트 베이스."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_path = os.path.join(self.tmp_dir, "project")
        os.makedirs(os.path.join(self.project_path, "audio", "scenes"))
        os.makedirs(os.path.join(self.project_path, "video"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_audio(self, path, seconds):
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{seconds:.2f}",
             "-i", "anullsrc=r=44100:cl=mono", "-c:a", "libmp3lame", path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def _make_video(self, path, seconds):
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{seconds:.2f}",
             "-i", "color=c=black:s=320x240", "-c:v", "libx264", path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class TestGetRealDurations(RealProjectFixture):

    def test_reports_scene_and_total_durations(self):
        self._make_audio(os.path.join(self.project_path, "audio", "scenes", "scene1.mp3"), 3.0)
        self._make_audio(os.path.join(self.project_path, "audio", "scenes", "scene2.mp3"), 4.0)
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 7.0)
        self._make_audio(os.path.join(self.project_path, "audio", "final_audio.mp3"), 7.0)
        self._make_video(os.path.join(self.project_path, "video", "final_short.mp4"), 7.0)

        result = get_real_durations(self.project_path)

        self.assertEqual(len(result["scenes"]), 2)
        self.assertAlmostEqual(result["scenes"][0]["duration"], 3.0, delta=0.1)
        self.assertAlmostEqual(result["scenes"][1]["duration"], 4.0, delta=0.1)
        self.assertAlmostEqual(result["voice"], 7.0, delta=0.1)
        self.assertAlmostEqual(result["final_audio"], 7.0, delta=0.1)
        self.assertAlmostEqual(result["final_video"], 7.0, delta=0.1)

    def test_missing_files_are_none_not_error(self):
        result = get_real_durations(self.project_path)

        self.assertEqual(result["scenes"], [])
        self.assertIsNone(result["voice"])
        self.assertIsNone(result["final_audio"])
        self.assertIsNone(result["final_video"])

    def test_scenes_are_sorted_numerically(self):
        for i in [2, 10, 1]:
            self._make_audio(
                os.path.join(self.project_path, "audio", "scenes", f"scene{i}.mp3"), 1.0
            )

        result = get_real_durations(self.project_path)

        self.assertEqual([s["scene"] for s in result["scenes"]], [1, 2, 10])


class TestLoadQualitySummary(unittest.TestCase):

    def test_missing_quality_report_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertIsNone(load_quality_summary(tmp_dir))

    def test_extracts_passed_and_checks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = {
                "technical_validation": {
                    "passed": True,
                    "checks": {
                        "video_duration": {"passed": True, "duration_seconds": 45.0},
                        "audio_video_sync": {"passed": True, "delta_ms": 5.0},
                    },
                    "blocking_failures": [],
                }
            }
            with open(os.path.join(tmp_dir, "quality_report.json"), "w", encoding="utf-8") as f:
                json.dump(report, f)

            summary = load_quality_summary(tmp_dir)

            self.assertTrue(summary["passed"])
            self.assertEqual(summary["blocking_failures"], [])
            self.assertTrue(summary["checks"]["video_duration"]["passed"])


class TestBuildQaReport(RealProjectFixture):

    def test_combines_durations_and_quality_summary(self):
        self._make_audio(os.path.join(self.project_path, "audio", "scenes", "scene1.mp3"), 5.0)
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 5.0)
        self._make_audio(os.path.join(self.project_path, "audio", "final_audio.mp3"), 5.0)
        self._make_video(os.path.join(self.project_path, "video", "final_short.mp4"), 5.0)

        report = build_qa_report(self.project_path)

        self.assertIn("durations", report)
        self.assertIn("quality", report)
        self.assertIn("target_range_ok", report)

    def test_target_range_ok_true_when_within_43_47(self):
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 45.0)
        self._make_video(os.path.join(self.project_path, "video", "final_short.mp4"), 45.0)

        report = build_qa_report(self.project_path)

        self.assertTrue(report["target_range_ok"])

    def test_target_range_ok_false_when_outside_43_47(self):
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 30.0)
        self._make_video(os.path.join(self.project_path, "video", "final_short.mp4"), 30.0)

        report = build_qa_report(self.project_path)

        self.assertFalse(report["target_range_ok"])

    def test_format_report_does_not_raise(self):
        self._make_audio(os.path.join(self.project_path, "audio", "voice.mp3"), 45.0)

        report = build_qa_report(self.project_path)
        text = format_report(report)

        self.assertIsInstance(text, str)
        self.assertIn(self.project_path, text)


if __name__ == "__main__":
    unittest.main()
