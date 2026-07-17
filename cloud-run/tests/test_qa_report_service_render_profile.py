"""
Sprint123 (GREEN) - qa_report_service가 render_profile을 안 넘기면
(기본값 None) script.json에 저장된 render_profile을 자동으로 읽어
Longform 산출물(final_longform.mp4)을 올바르게 찾는다. script.json이
없거나 render_profile 키가 없으면(기존 Shorts 프로젝트) 100% 기존과
동일하게 동작한다.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import qa_report_service
from app.services.render_profile import RenderProfile


LONGFORM = RenderProfile.get("longform")


def _make_silent_mp3(path, duration=1.0):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-t", str(duration),
         "-i", "anullsrc=r=44100:cl=mono", "-c:a", "libmp3lame", path],
        capture_output=True, check=True,
    )


class TestGetRealDurationsRenderProfile(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name
        os.makedirs(os.path.join(self.project_path, "video"))
        os.makedirs(os.path.join(self.project_path, "audio", "scenes"))

    def test_default_reads_final_short(self):
        _make_silent_mp3(os.path.join(self.project_path, "video", "final_short.mp4"))

        durations = qa_report_service.get_real_durations(self.project_path)
        self.assertIsNotNone(durations["final_video"])

    def test_longform_reads_final_longform(self):
        _make_silent_mp3(os.path.join(self.project_path, "video", "final_longform.mp4"))

        durations = qa_report_service.get_real_durations(
            self.project_path, render_profile=LONGFORM,
        )
        self.assertIsNotNone(durations["final_video"])

    def test_default_does_not_find_final_longform(self):
        _make_silent_mp3(os.path.join(self.project_path, "video", "final_longform.mp4"))

        durations = qa_report_service.get_real_durations(self.project_path)
        self.assertIsNone(durations["final_video"])


class TestBuildQaReportAutoDetectsRenderProfile(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name
        os.makedirs(os.path.join(self.project_path, "video"))
        os.makedirs(os.path.join(self.project_path, "audio", "scenes"))

    def test_auto_detects_longform_from_script_json(self):
        with open(os.path.join(self.project_path, "script.json"), "w", encoding="utf-8") as f:
            json.dump({"scenes": [], "render_profile": LONGFORM}, f)

        _make_silent_mp3(os.path.join(self.project_path, "video", "final_longform.mp4"))

        report = qa_report_service.build_qa_report(self.project_path)

        self.assertEqual(report["final_video_filename"], "final_longform.mp4")
        self.assertIsNotNone(report["durations"]["final_video"])

    def test_no_script_json_defaults_to_shorts(self):
        _make_silent_mp3(os.path.join(self.project_path, "video", "final_short.mp4"))

        report = qa_report_service.build_qa_report(self.project_path)

        self.assertEqual(report["final_video_filename"], "final_short.mp4")


if __name__ == "__main__":
    unittest.main()
