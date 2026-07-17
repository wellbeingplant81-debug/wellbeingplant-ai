import contextlib
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

FAKE_PROMPT_METRICS = [
    {"scene_id": 1, "score": 100, "passed": True, "metrics": {}},
    {"scene_id": 2, "score": 60, "passed": False, "metrics": {}},
]

FAKE_DIRECTOR_DECISION = [
    {"scene_id": 1, "decision": "accept", "confidence": 0.95, "reasons": ["prompt_passed"]},
    {"scene_id": 2, "decision": "regenerate", "confidence": 0.3, "reasons": ["prompt_failed"]},
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
         patch("app.pipeline.pipeline.prompt_learning_service") as prompt_learning, \
         patch("app.pipeline.pipeline.ai_director_service") as ai_director, \
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
            "prompt_learning": prompt_learning,
            "ai_director": ai_director,
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


class TestAiDirectorFeatureFlag(unittest.TestCase):

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

            m["ai_director"].evaluate_scenes.assert_not_called()
            self.assertNotIn("director_decision", result)
            self.assertEqual(result["scenes"], ENRICHED_SCENES)

    def test_flag_on_calls_evaluate_scenes_and_stores_result(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_EFFECTIVENESS", True), \
             patch("app.pipeline.pipeline.config.ENABLE_AI_DIRECTOR", True):
            _wire_defaults(m)
            m["prompt_effectiveness"].evaluate_scenes.return_value = FAKE_PROMPT_METRICS
            m["ai_director"].evaluate_scenes.return_value = FAKE_DIRECTOR_DECISION

            result = self._run_pipeline()

            m["ai_director"].evaluate_scenes.assert_called_once()
            call_args = m["ai_director"].evaluate_scenes.call_args[0]
            self.assertEqual(call_args[0], STYLED_SCENES)
            self.assertIsNone(call_args[1])
            self.assertEqual(call_args[2], FAKE_PROMPT_METRICS)
            self.assertEqual(result["director_decision"], FAKE_DIRECTOR_DECISION)

    def test_director_never_changes_scenes_or_other_output(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_EFFECTIVENESS", True), \
             patch("app.pipeline.pipeline.config.ENABLE_AI_DIRECTOR", True):
            _wire_defaults(m)
            m["prompt_effectiveness"].evaluate_scenes.return_value = FAKE_PROMPT_METRICS
            m["ai_director"].evaluate_scenes.return_value = FAKE_DIRECTOR_DECISION

            result = self._run_pipeline()

            self.assertEqual(result["scenes"], ENRICHED_SCENES)
            m["step02_assets"].collect_assets.assert_called_once_with(
                STYLED_SCENES, self.project_path, "wellbeing",
            )

    def test_missing_metrics_still_calls_director_gracefully(self):
        """Effectiveness가 꺼져 있어 prompt_metrics가 없어도 Director
        플래그가 켜져 있으면 실행되어야 한다(모두 unknown으로 처리)."""

        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_AI_DIRECTOR", True):
            _wire_defaults(m)
            m["ai_director"].evaluate_scenes.return_value = FAKE_DIRECTOR_DECISION

            result = self._run_pipeline()

            m["ai_director"].evaluate_scenes.assert_called_once()
            call_args = m["ai_director"].evaluate_scenes.call_args[0]
            self.assertIsNone(call_args[2])
            self.assertEqual(result["director_decision"], FAKE_DIRECTOR_DECISION)

    def test_exception_does_not_break_pipeline(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PROMPT_EFFECTIVENESS", True), \
             patch("app.pipeline.pipeline.config.ENABLE_AI_DIRECTOR", True):
            _wire_defaults(m)
            m["prompt_effectiveness"].evaluate_scenes.return_value = FAKE_PROMPT_METRICS
            m["ai_director"].evaluate_scenes.side_effect = Exception("director boom")

            result = self._run_pipeline()

            self.assertNotIn("director_decision", result)
            self.assertEqual(result["scenes"], ENRICHED_SCENES)
            m["step03"].run.assert_called_once_with(ENRICHED_SCENES, self.project_path)
            m["regeneration_service"].run.assert_called_once_with(self.project_path)

    def test_default_flags_off_pipeline_output_unchanged_from_sprint49(self):
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
