import contextlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.pipeline import pipeline


SAMPLE_DATA = {
    "title": "t",
    "hook": "h",
    "script": "s",
    "scenes": [
        {"scene": 1, "narration": "n1", "image_prompt": "p1"},
        {"scene": 2, "narration": "n2", "image_prompt": "p2"},
    ],
}

STYLED_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1 styled"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2 styled"},
]

ENRICHED_PROMPT_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1 styled, close-up"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2 styled, medium shot"},
]

OPTIMIZED_PROMPT_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1 styled, close-up, hook"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2 styled, medium shot, cta"},
]

ENRICHED_SCENES = [
    {
        "scene": 1, "narration": "n1", "image_prompt": "p1 styled",
        "asset_path": "images/scene1.png", "provider": "ai_image",
        "asset_type": "image", "search_query": "q1", "confidence": 1.0,
    },
    {
        "scene": 2, "narration": "n2", "image_prompt": "p2 styled",
        "asset_path": "images/scene2.png", "provider": "pexels_image",
        "asset_type": "image", "search_query": "q2", "confidence": 0.8,
    },
]

FAKE_SCENE_PLAN = [
    {"scene_id": 1, "purpose": "hook", "visual_type": "photo_realistic",
     "camera": "close_up", "transition": "fade", "duration": 3.0, "keywords": ["k1"]},
    {"scene_id": 2, "purpose": "cta", "visual_type": "photo_realistic",
     "camera": "medium_shot", "transition": "cross_dissolve", "duration": 3.0, "keywords": ["k2"]},
]

FAKE_PROMPT_METRICS = [
    {"scene_id": 1, "score": 70, "passed": False, "metrics": {"purpose": False}},
    {"scene_id": 2, "score": 70, "passed": False, "metrics": {"purpose": False}},
]


@contextlib.contextmanager
def patched_pipeline():
    with patch("app.pipeline.pipeline.step01_script") as step01, \
         patch("app.pipeline.pipeline.step02_assets") as step02_assets, \
         patch("app.pipeline.pipeline.step03_tts") as step03, \
         patch("app.pipeline.pipeline.step04_subtitle") as step04, \
         patch("app.pipeline.pipeline.step05_video") as step05, \
         patch("app.pipeline.pipeline.step06_thumbnail") as step06, \
         patch("app.pipeline.pipeline.step07_quality") as step07, \
         patch("app.pipeline.pipeline.regeneration_service") as regeneration_service, \
         patch("app.pipeline.pipeline.visual_consistency_engine") as visual_consistency, \
         patch("app.pipeline.pipeline.scene_planner_service") as scene_planner, \
         patch("app.pipeline.pipeline.prompt_enrichment_service") as prompt_enrichment, \
         patch("app.pipeline.pipeline.prompt_effectiveness_service") as prompt_effectiveness, \
         patch("app.pipeline.pipeline.prompt_optimization_service") as prompt_optimization, \
         patch("app.pipeline.pipeline.thumbnail_headline_service") as thumbnail_headline_service:

        thumbnail_headline_service.generate_thumbnail_headline.return_value = {
            "lines": ["헤드라인"], "keywords": [],
        }

        yield {
            "step01": step01,
            "step02_assets": step02_assets,
            "step03": step03,
            "step04": step04,
            "step05": step05,
            "step06": step06,
            "step07": step07,
            "regeneration_service": regeneration_service,
            "visual_consistency": visual_consistency,
            "scene_planner": scene_planner,
            "prompt_enrichment": prompt_enrichment,
            "prompt_effectiveness": prompt_effectiveness,
            "prompt_optimization": prompt_optimization,
            "thumbnail_headline_service": thumbnail_headline_service,
        }


def _wire_defaults(mocks):
    mocks["step01"].run.return_value = dict(SAMPLE_DATA)
    mocks["visual_consistency"].apply_visual_consistency.return_value = STYLED_SCENES
    # Sprint60 - apply_visual_type을 항등 함수로 둬서(scenes 그대로
    # 통과), collect_assets 호출 인자를 검증하는 기존 테스트들이
    # visual_type 분기 도입과 무관하게 그대로 성립하도록 한다.
    mocks["scene_planner"].apply_visual_type.side_effect = lambda scenes: scenes
    mocks["step02_assets"].collect_assets.return_value = ENRICHED_SCENES


class TestPromptOptimizationFeatureFlag(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def _run_pipeline(self):
        return pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
        )

    def test_flag_off_is_never_called(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_EFFECTIVENESS", True):
            _wire_defaults(m)
            m["prompt_effectiveness"].evaluate_scenes.return_value = FAKE_PROMPT_METRICS

            result = self._run_pipeline()

            m["prompt_optimization"].optimize_scenes.assert_not_called()
            self.assertEqual(result["scenes"], ENRICHED_SCENES)

    def test_flag_on_with_prompt_metrics_applies_optimization_before_asset_collection(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_SCENE_PLANNER", True), \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_ENRICHMENT", True), \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_EFFECTIVENESS", True), \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_OPTIMIZATION", True):
            _wire_defaults(m)
            m["scene_planner"].plan_scenes.return_value = FAKE_SCENE_PLAN
            m["prompt_enrichment"].apply_prompt_enrichment.return_value = ENRICHED_PROMPT_SCENES
            m["prompt_effectiveness"].evaluate_scenes.return_value = FAKE_PROMPT_METRICS
            m["prompt_optimization"].optimize_scenes.return_value = OPTIMIZED_PROMPT_SCENES

            self._run_pipeline()

            m["prompt_optimization"].optimize_scenes.assert_called_once_with(
                STYLED_SCENES, ENRICHED_PROMPT_SCENES, FAKE_PROMPT_METRICS, FAKE_SCENE_PLAN,
            )
            m["step02_assets"].collect_assets.assert_called_once_with(
                OPTIMIZED_PROMPT_SCENES, self.project_path, "wellbeing",
            )

    def test_flag_on_without_prompt_metrics_leaves_prompts_unchanged(self):
        """Effectiveness가 비활성화되어 있으면(prompt_metrics 없음)
        Optimization 플래그가 켜져 있어도 기존 결과와 동일해야 한다."""

        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_OPTIMIZATION", True):
            _wire_defaults(m)

            result = self._run_pipeline()

            m["prompt_optimization"].optimize_scenes.assert_not_called()
            self.assertEqual(result["scenes"], ENRICHED_SCENES)

    def test_optimization_exception_does_not_break_pipeline(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_EFFECTIVENESS", True), \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_OPTIMIZATION", True):
            _wire_defaults(m)
            m["prompt_effectiveness"].evaluate_scenes.return_value = FAKE_PROMPT_METRICS
            m["prompt_optimization"].optimize_scenes.side_effect = Exception("optimize boom")

            result = self._run_pipeline()

            self.assertEqual(result["scenes"], ENRICHED_SCENES)
            m["step02_assets"].collect_assets.assert_called_once_with(
                STYLED_SCENES, self.project_path, "wellbeing",
            )
            m["regeneration_service"].run.assert_called_once_with(self.project_path)

    def test_default_flags_off_pipeline_output_unchanged_from_sprint47(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            result = self._run_pipeline()

            self.assertEqual(
                result,
                {
                    "title": "t",
                    "hook": "h",
                    "script": "s",
                    "scenes": ENRICHED_SCENES,
                    "thumbnail_headline": {"lines": ["헤드라인"], "keywords": []},
                },
            )
            m["step02_assets"].collect_assets.assert_called_once_with(
                STYLED_SCENES, self.project_path, "wellbeing",
            )


if __name__ == "__main__":
    unittest.main()
