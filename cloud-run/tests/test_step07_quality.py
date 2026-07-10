import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.quality_report import QualityReport, QualityReportMetadata, VisualDiversitySummary
from app.steps.step07_quality import _build_visual_diversity_summary


PROFILE_A = {
    "camera_distance": "wide", "camera_angle": "eye level",
    "composition": "centered", "lighting": "soft daylight",
}
PROFILE_B = {
    "camera_distance": "macro", "camera_angle": "top-down",
    "composition": "leading lines", "lighting": "backlit",
}


class TestBuildVisualDiversitySummary(unittest.TestCase):
    """
    Sprint72-3 - Visual Diversity QA. quality_report.json(실제 파일,
    app/models/quality_report.py의 QualityReport)에 실을 요약을
    data["scenes"](step07_quality.run()에 넘어오는 enriched scene
    목록, Sprint72-2 이후 scene["visual_profile"]을 가질 수 있음)로부터
    만든다. 새 판정 로직 없이 visual_diversity_engine.summarize_
    visual_diversity()를 그대로 재사용한다.
    """

    def test_no_scenes_returns_none(self):
        self.assertIsNone(_build_visual_diversity_summary([]))

    def test_none_scenes_returns_none(self):
        self.assertIsNone(_build_visual_diversity_summary(None))

    def test_scenes_without_any_visual_profile_returns_none(self):
        # 요구사항: profile=None(전혀 없음)이면 완전 no-op.
        scenes = [
            {"scene": 1, "asset_path": "a.png"},
            {"scene": 2, "asset_path": "b.png"},
        ]
        self.assertIsNone(_build_visual_diversity_summary(scenes))

    def test_scenes_with_profiles_returns_populated_summary(self):
        scenes = [
            {"scene": 1, "asset_path": "a.png", "visual_profile": PROFILE_A},
            {"scene": 2, "asset_path": "b.png", "visual_profile": PROFILE_B},
        ]

        summary = _build_visual_diversity_summary(scenes)

        self.assertIsInstance(summary, VisualDiversitySummary)
        self.assertEqual(summary.camera_distance_diversity_count, 2)
        self.assertEqual(summary.camera_angle_diversity_count, 2)

    def test_profiles_by_scene_recorded(self):
        scenes = [{"scene": 1, "asset_path": "a.png", "visual_profile": PROFILE_A}]

        summary = _build_visual_diversity_summary(scenes)

        self.assertEqual(summary.profiles_by_scene[1], PROFILE_A)

    def test_scenes_missing_visual_profile_key_are_skipped_not_broken(self):
        # 일부 scene만 visual_profile을 가진 혼합 상황(예: 파이프라인
        # 중간 데이터, 또는 요구사항 "visual_profile이 없는 Scene은
        # 기존 동작 유지")도 크래시 없이 있는 것만 집계해야 한다.
        scenes = [
            {"scene": 1, "asset_path": "a.png", "visual_profile": PROFILE_A},
            {"scene": 2, "asset_path": "b.png"},
        ]

        summary = _build_visual_diversity_summary(scenes)

        self.assertEqual(len(summary.profiles_by_scene), 1)
        self.assertIn(1, summary.profiles_by_scene)


class TestQualityReportModelBackwardCompatible(unittest.TestCase):
    """visual_diversity 필드는 기본값 None이라, 기존(Sprint72-3 이전)
    quality_report.json 데이터를 그대로 파싱해도 깨지지 않아야 한다."""

    def _minimal_report_kwargs(self):
        return dict(
            project_id="p1",
            technical_validation={
                "passed": True,
                "checks": {
                    "required_files_exist": {"passed": True, "missing": []},
                    "scene_count_consistency": {
                        "passed": True, "script_scenes": 1,
                        "image_files": 1, "audio_files": 1,
                    },
                    "image_resolution": {"passed": True, "warnings": [], "details": []},
                    "video_duration": {"passed": True, "duration_seconds": 45.0},
                    "subtitle_existence": {"passed": True, "cue_count": 3},
                    "audio_video_sync": {
                        "passed": True, "video_duration_seconds": 45.0,
                        "audio_duration_seconds": 45.0, "delta_ms": 0.0,
                        "tolerance_ms": 250.0,
                    },
                    "thumbnail_existence": {"passed": True},
                },
                "performance_metrics": {
                    "project_creation_seconds": 0.0, "script_generation_seconds": 0.0,
                    "image_generation_seconds": 0.0, "tts_generation_seconds": 0.0,
                    "subtitle_generation_seconds": 0.0, "video_rendering_seconds": 0.0,
                    "thumbnail_generation_seconds": 0.0, "quality_evaluation_seconds": 0.0,
                    "total_generation_time_seconds": 0.0, "final_file_size_bytes": 0,
                    "thumbnail_file_size_bytes": 0,
                },
                "blocking_failures": [],
            },
            metadata=QualityReportMetadata(
                evaluated_at="2026-01-01T00:00:00Z", schema_version="sprint23",
            ),
        )

    def test_visual_diversity_defaults_to_none(self):
        report = QualityReport(**self._minimal_report_kwargs())
        self.assertIsNone(report.visual_diversity)

    def test_visual_diversity_can_be_populated(self):
        summary = _build_visual_diversity_summary(
            [{"scene": 1, "asset_path": "a.png", "visual_profile": PROFILE_A}]
        )
        kwargs = self._minimal_report_kwargs()
        kwargs["visual_diversity"] = summary

        report = QualityReport(**kwargs)

        self.assertIsNotNone(report.visual_diversity)
        self.assertEqual(report.visual_diversity.camera_distance_diversity_count, 1)

    def test_model_dump_round_trips_through_json(self):
        import json

        summary = _build_visual_diversity_summary(
            [{"scene": 1, "asset_path": "a.png", "visual_profile": PROFILE_A}]
        )
        kwargs = self._minimal_report_kwargs()
        kwargs["visual_diversity"] = summary

        report = QualityReport(**kwargs)
        dumped = json.loads(json.dumps(report.model_dump(), ensure_ascii=False))

        self.assertIn("visual_diversity", dumped)
        self.assertEqual(
            dumped["visual_diversity"]["camera_distance_diversity_count"], 1,
        )


if __name__ == "__main__":
    unittest.main()
