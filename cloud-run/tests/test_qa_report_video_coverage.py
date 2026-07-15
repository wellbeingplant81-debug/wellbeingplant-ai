"""
Sprint102 - Video Coverage Intelligence QA. qa_report_service.
build_video_coverage_summary()가 script.json scene의 assets[0].
video_path/motion_contract.video_intent/selection_trace를 읽기 전용
으로 집계하는지 확인한다(Video/Image Scene 수, Render Mode, Search
Query Cascade). motion_contract/selection_trace가 없는 기존 scene도
크래시 없이 처리돼야 한다(하위 호환).
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


class TestBuildVideoCoverageSummary(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def test_no_script_json_returns_zero_counts(self):
        summary = qa_report_service.build_video_coverage_summary(self.project_path)
        self.assertEqual(summary["video_scene_count"], 0)
        self.assertEqual(summary["image_scene_count"], 0)
        self.assertEqual(summary["scenes"], [])

    def test_counts_video_and_image_scenes_by_video_path_presence(self):
        _write_script(self.project_path, [
            {"scene": 1, "assets": [{"path": "a.png", "video_path": "a.mp4"}]},
            {"scene": 2, "assets": [{"path": "b.png"}]},
            {"scene": 3, "assets": [{"path": "c.png"}]},
        ])

        summary = qa_report_service.build_video_coverage_summary(self.project_path)

        self.assertEqual(summary["video_scene_count"], 1)
        self.assertEqual(summary["image_scene_count"], 2)

    def test_render_mode_labels_match_video_path_presence(self):
        _write_script(self.project_path, [
            {"scene": 1, "assets": [{"path": "a.png", "video_path": "a.mp4"}]},
            {"scene": 2, "assets": [{"path": "b.png"}]},
        ])

        summary = qa_report_service.build_video_coverage_summary(self.project_path)

        by_scene = {e["scene"]: e for e in summary["scenes"]}
        self.assertEqual(by_scene[1]["render_mode"], "VideoFileClip")
        self.assertEqual(by_scene[2]["render_mode"], "Ken Burns (Image)")

    def test_video_intent_read_from_motion_contract(self):
        _write_script(self.project_path, [
            {
                "scene": 1,
                "assets": [{"path": "a.png"}],
                "motion_contract": {
                    "video_intent": {
                        "intent": "preferred_video", "confidence": 0.9,
                        "reason": "r", "source": "ai_classifier",
                    },
                },
            },
        ])

        summary = qa_report_service.build_video_coverage_summary(self.project_path)

        self.assertEqual(summary["scenes"][0]["video_intent"], "preferred_video")
        self.assertEqual(summary["scenes"][0]["video_intent_source"], "ai_classifier")

    def test_missing_motion_contract_does_not_crash(self):
        _write_script(self.project_path, [
            {"scene": 1, "assets": [{"path": "a.png"}]},
        ])

        summary = qa_report_service.build_video_coverage_summary(self.project_path)

        self.assertIsNone(summary["scenes"][0]["video_intent"])
        self.assertIsNone(summary["scenes"][0]["video_intent_source"])

    def test_search_query_cascade_deduplicated_in_order(self):
        trace = [
            {"search_query": "primary query", "score": 0.2},
            {"search_query": "primary query", "score": 0.1},
            {"search_query": "action query", "score": 0.8},
        ]
        _write_script(self.project_path, [
            {"scene": 1, "assets": [{"path": "a.png"}], "selection_trace": trace},
        ])

        summary = qa_report_service.build_video_coverage_summary(self.project_path)

        self.assertEqual(
            summary["scenes"][0]["search_query_cascade"],
            ["primary query", "action query"],
        )

    def test_format_report_prints_video_coverage_section(self):
        _write_script(self.project_path, [
            {"scene": 1, "assets": [{"path": "a.png", "video_path": "a.mp4"}]},
            {"scene": 2, "assets": [{"path": "b.png"}]},
        ])

        report = qa_report_service.build_qa_report(self.project_path)
        text = qa_report_service.format_report(report)

        self.assertIn("Video Coverage (Sprint102):", text)
        self.assertIn("Video: 1 Scene", text)
        self.assertIn("Image: 1 Scene", text)

    def test_format_report_omits_section_when_no_scenes(self):
        _write_script(self.project_path, [])

        report = qa_report_service.build_qa_report(self.project_path)
        text = qa_report_service.format_report(report)

        self.assertNotIn("Video Coverage (Sprint102):", text)


if __name__ == "__main__":
    unittest.main()
