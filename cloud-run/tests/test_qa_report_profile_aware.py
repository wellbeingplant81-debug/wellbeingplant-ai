"""
Sprint100-1 - QA Report Production Profile Awareness.

qa_report_service.build_qa_report()가 target_range_ok를 항상 하드코딩된
43~47초(development profile 기준)로 판정해, upload profile(ElevenLabs,
duration_target=55)로 만든 영상은 정상이어도 "OUT OF RANGE"로 잘못
보고되는 문제(Sprint97 Production QA에서 발견)를 고친다.

script.json에 production_profile(ProductionProfileIntegration이 채운,
Sprint93+)이 있으면 그 duration_target ± tolerance(pipeline.py의
DURATION_TOLERANCE_SECONDS=2와 동일)를 목표 범위로 쓴다. 없으면(레거시
데이터/ENABLE_PRODUCTION_PROFILE 꺼짐) 기존 43~47초를 그대로 쓴다 -
완전히 하위 호환.
"""

import json
import os
import subprocess
import tempfile
import unittest

from app.services import qa_report_service


class ProjectFixture(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name
        os.makedirs(os.path.join(self.project_path, "video"))

    def _make_video(self, seconds):
        path = os.path.join(self.project_path, "video", "final_short.mp4")
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", f"{seconds:.2f}",
             "-i", "color=c=black:s=320x240", "-c:v", "libx264", path],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def _write_script(self, production_profile=None):
        data = {"scenes": []}
        if production_profile is not None:
            data["production_profile"] = production_profile
        with open(os.path.join(self.project_path, "script.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)


class TestTargetRangeProfileAware(ProjectFixture):

    def test_uses_upload_profile_duration_target(self):
        self._write_script({
            "profile": "upload",
            "duration_target": 55,
            "tts_provider": "elevenlabs",
            "asset_strategy": "upload",
        })
        self._make_video(54.0)

        report = qa_report_service.build_qa_report(self.project_path)

        self.assertTrue(report["target_range_ok"])
        self.assertEqual(report["target_min_seconds"], 53)
        self.assertEqual(report["target_max_seconds"], 57)

    def test_upload_profile_duration_outside_its_own_range_fails(self):
        self._write_script({
            "profile": "upload",
            "duration_target": 55,
            "tts_provider": "elevenlabs",
            "asset_strategy": "upload",
        })
        # 44s would pass the OLD hardcoded 43-47 range but must fail the
        # correct 53-57 range for an upload-profile project.
        self._make_video(44.0)

        report = qa_report_service.build_qa_report(self.project_path)

        self.assertFalse(report["target_range_ok"])

    def test_falls_back_to_default_range_without_production_profile(self):
        self._write_script(production_profile=None)
        self._make_video(45.0)

        report = qa_report_service.build_qa_report(self.project_path)

        self.assertTrue(report["target_range_ok"])
        self.assertEqual(report["target_min_seconds"], 43.0)
        self.assertEqual(report["target_max_seconds"], 47.0)

    def test_falls_back_to_default_range_without_script_json(self):
        self._make_video(45.0)

        report = qa_report_service.build_qa_report(self.project_path)

        self.assertTrue(report["target_range_ok"])
        self.assertEqual(report["target_min_seconds"], 43.0)
        self.assertEqual(report["target_max_seconds"], 47.0)

    def test_format_report_shows_profile_specific_range_text(self):
        self._write_script({
            "profile": "upload",
            "duration_target": 55,
            "tts_provider": "elevenlabs",
            "asset_strategy": "upload",
        })
        self._make_video(54.0)

        report = qa_report_service.build_qa_report(self.project_path)
        text = qa_report_service.format_report(report)

        self.assertIn("53-57s", text)


if __name__ == "__main__":
    unittest.main()
