"""
Sprint100-3.1 - qa_report_service가 script.json scene의 video_relevance_
trace(asset_integration_service._select_relevant_video_candidate()가
남긴 값)를 읽기 전용으로 리포트/텍스트에 노출하는지 확인한다. trace가
없는 scene(기존 프로젝트/video 후보를 채점하지 않은 scene)은 기존과
완전히 동일해야 한다.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import qa_report_service


def _write_script(project_path, scenes):
    with open(os.path.join(project_path, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes}, f)


class TestVideoRelevanceTrace(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def test_trace_included_when_present(self):
        trace = [
            {"candidate": "walking", "score": 0.91, "reasoning": "일치"},
            {"candidate": "gym", "score": 0.3, "reasoning": "무관"},
        ]
        _write_script(self.project_path, [
            {"scene": 1, "asset_path": "a.png", "video_relevance_trace": trace},
        ])

        summary = qa_report_service.build_asset_intelligence_summary(self.project_path)

        self.assertEqual(summary[0]["video_relevance_trace"], trace)

    def test_trace_is_none_when_absent(self):
        _write_script(self.project_path, [
            {"scene": 1, "asset_path": "a.png"},
        ])

        summary = qa_report_service.build_asset_intelligence_summary(self.project_path)

        self.assertIsNone(summary[0]["video_relevance_trace"])

    def test_format_report_prints_trace_section(self):
        trace = [
            {"candidate": "walking", "score": 0.91, "reasoning": "일치"},
            {"candidate": "gym", "score": 0.3, "reasoning": "무관"},
        ]
        _write_script(self.project_path, [
            {"scene": 3, "asset_path": "a.png", "video_relevance_trace": trace},
        ])

        report = qa_report_service.build_qa_report(self.project_path)
        text = qa_report_service.format_report(report)

        self.assertIn("Stock Video Relevance Trace", text)
        self.assertIn("Scene3", text)
        self.assertIn("walking", text)
        self.assertIn("0.91", text)

    def test_format_report_omits_trace_section_when_no_scene_has_trace(self):
        _write_script(self.project_path, [
            {"scene": 1, "asset_path": "a.png"},
        ])

        report = qa_report_service.build_qa_report(self.project_path)
        text = qa_report_service.format_report(report)

        self.assertNotIn("Stock Video Relevance Trace", text)

    def test_format_report_prints_error_entries(self):
        trace = [{"candidate": "walking", "error": "download failed"}]
        _write_script(self.project_path, [
            {"scene": 2, "asset_path": "a.png", "video_relevance_trace": trace},
        ])

        report = qa_report_service.build_qa_report(self.project_path)
        text = qa_report_service.format_report(report)

        self.assertIn("error: download failed", text)


if __name__ == "__main__":
    unittest.main()
