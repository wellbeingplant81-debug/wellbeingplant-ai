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

# Sprint60 - 이 테스트 파일은 scene_planner_service를 mock하지 않으므로
# 실제 apply_visual_type()이 실행돼 STYLED_SCENES에 visual_type을 채운
# 뒤 step02_assets.collect_assets로 넘어간다("n1"/"n2", "p1 styled"/
# "p2 styled"에는 real/ai 키워드가 없어 기본값인 "real"이 된다).
VISUAL_TYPED_SCENES = [
    {**scene, "visual_type": "real"} for scene in STYLED_SCENES
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


class TestPipeline(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

        # Sprint124 - thumbnail_headline_service는 실제 Gemini를
        # 호출하므로, 이 파일의 모든 테스트에서 공통으로 mock한다
        # (기존 테스트들이 이 서비스를 몰라도 되도록 데코레이터가
        # 아니라 setUp에서 한 번만 patch).
        headline_patcher = patch("app.pipeline.pipeline.thumbnail_headline_service")
        self.addCleanup(headline_patcher.stop)
        mock_headline_service = headline_patcher.start()
        mock_headline_service.generate_thumbnail_headline.return_value = {
            "lines": ["헤드라인"], "keywords": [],
        }

    @patch("app.pipeline.pipeline.regeneration_service")
    @patch("app.pipeline.pipeline.visual_consistency_engine")
    @patch("app.pipeline.pipeline.step01_script")
    @patch("app.pipeline.pipeline.step02_assets")
    @patch("app.pipeline.pipeline.step03_tts")
    @patch("app.pipeline.pipeline.step04_subtitle")
    @patch("app.pipeline.pipeline.step05_video")
    @patch("app.pipeline.pipeline.step06_thumbnail")
    @patch("app.pipeline.pipeline.step07_quality")
    def test_pipeline_calls_step02_assets_with_correct_args(
        self,
        mock_step07,
        mock_step06,
        mock_step05,
        mock_step04,
        mock_step03,
        mock_step02_assets,
        mock_step01,
        mock_visual_consistency,
        mock_regeneration_service,
    ):
        mock_step01.run.return_value = dict(SAMPLE_DATA)
        mock_visual_consistency.apply_visual_consistency.return_value = STYLED_SCENES
        mock_step02_assets.collect_assets.return_value = ENRICHED_SCENES

        result = pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
        )

        mock_visual_consistency.apply_visual_consistency.assert_called_once_with(
            SAMPLE_DATA["scenes"], "wellbeing",
        )
        mock_step02_assets.collect_assets.assert_called_once_with(
            VISUAL_TYPED_SCENES, self.project_path, "wellbeing",
        )
        self.assertEqual(result["scenes"], ENRICHED_SCENES)

    @patch("app.pipeline.pipeline.regeneration_service")
    @patch("app.pipeline.pipeline.visual_consistency_engine")
    @patch("app.pipeline.pipeline.step01_script")
    @patch("app.pipeline.pipeline.step02_assets")
    @patch("app.pipeline.pipeline.step03_tts")
    @patch("app.pipeline.pipeline.step04_subtitle")
    @patch("app.pipeline.pipeline.step05_video")
    @patch("app.pipeline.pipeline.step06_thumbnail")
    @patch("app.pipeline.pipeline.step07_quality")
    def test_script_json_written_once_with_enriched_scenes(
        self,
        mock_step07,
        mock_step06,
        mock_step05,
        mock_step04,
        mock_step03,
        mock_step02_assets,
        mock_step01,
        mock_visual_consistency,
        mock_regeneration_service,
    ):
        mock_step01.run.return_value = dict(SAMPLE_DATA)
        mock_visual_consistency.apply_visual_consistency.return_value = STYLED_SCENES
        mock_step02_assets.collect_assets.return_value = ENRICHED_SCENES

        pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
        )

        script_path = os.path.join(self.project_path, "script.json")
        self.assertTrue(os.path.exists(script_path))

        with open(script_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["scenes"], ENRICHED_SCENES)
        self.assertEqual(saved["title"], SAMPLE_DATA["title"])

    @patch("app.pipeline.pipeline.regeneration_service")
    @patch("app.pipeline.pipeline.visual_consistency_engine")
    @patch("app.pipeline.pipeline.step01_script")
    @patch("app.pipeline.pipeline.step02_assets")
    @patch("app.pipeline.pipeline.step03_tts")
    @patch("app.pipeline.pipeline.step04_subtitle")
    @patch("app.pipeline.pipeline.step05_video")
    @patch("app.pipeline.pipeline.step06_thumbnail")
    @patch("app.pipeline.pipeline.step07_quality")
    def test_downstream_steps_receive_enriched_scenes(
        self,
        mock_step07,
        mock_step06,
        mock_step05,
        mock_step04,
        mock_step03,
        mock_step02_assets,
        mock_step01,
        mock_visual_consistency,
        mock_regeneration_service,
    ):
        mock_step01.run.return_value = dict(SAMPLE_DATA)
        mock_visual_consistency.apply_visual_consistency.return_value = STYLED_SCENES
        mock_step02_assets.collect_assets.return_value = ENRICHED_SCENES

        pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
        )

        mock_step03.run.assert_called_once_with(ENRICHED_SCENES, self.project_path)

        _, thumbnail_args, _ = mock_step06.run.mock_calls[0]
        self.assertEqual(thumbnail_args[4], "n1")
        self.assertEqual(thumbnail_args[5], "p1 styled")

    def test_step02_image_not_used_by_pipeline_module(self):
        self.assertFalse(hasattr(pipeline, "step02_image"))

    @patch("app.pipeline.pipeline.regeneration_service")
    @patch("app.pipeline.pipeline.visual_consistency_engine")
    @patch("app.pipeline.pipeline.step01_script")
    @patch("app.pipeline.pipeline.step02_assets")
    @patch("app.pipeline.pipeline.step03_tts")
    @patch("app.pipeline.pipeline.step04_subtitle")
    @patch("app.pipeline.pipeline.step05_video")
    @patch("app.pipeline.pipeline.step06_thumbnail")
    @patch("app.pipeline.pipeline.step07_quality")
    def test_regeneration_service_runs_after_successful_quality_step(
        self,
        mock_step07,
        mock_step06,
        mock_step05,
        mock_step04,
        mock_step03,
        mock_step02_assets,
        mock_step01,
        mock_visual_consistency,
        mock_regeneration_service,
    ):
        mock_step01.run.return_value = dict(SAMPLE_DATA)
        mock_visual_consistency.apply_visual_consistency.return_value = STYLED_SCENES
        mock_step02_assets.collect_assets.return_value = ENRICHED_SCENES

        pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
        )

        mock_regeneration_service.run.assert_called_once_with(self.project_path)

    @patch("app.pipeline.pipeline.regeneration_service")
    @patch("app.pipeline.pipeline.visual_consistency_engine")
    @patch("app.pipeline.pipeline.step01_script")
    @patch("app.pipeline.pipeline.step02_assets")
    @patch("app.pipeline.pipeline.step03_tts")
    @patch("app.pipeline.pipeline.step04_subtitle")
    @patch("app.pipeline.pipeline.step05_video")
    @patch("app.pipeline.pipeline.step06_thumbnail")
    @patch("app.pipeline.pipeline.step07_quality")
    def test_regeneration_service_skipped_when_quality_step_raises(
        self,
        mock_step07,
        mock_step06,
        mock_step05,
        mock_step04,
        mock_step03,
        mock_step02_assets,
        mock_step01,
        mock_visual_consistency,
        mock_regeneration_service,
    ):
        mock_step01.run.return_value = dict(SAMPLE_DATA)
        mock_visual_consistency.apply_visual_consistency.return_value = STYLED_SCENES
        mock_step02_assets.collect_assets.return_value = ENRICHED_SCENES
        mock_step07.run.side_effect = Exception("boom")

        pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
        )

        mock_regeneration_service.run.assert_not_called()

    @patch("app.pipeline.pipeline.regeneration_service")
    @patch("app.pipeline.pipeline.visual_consistency_engine")
    @patch("app.pipeline.pipeline.step01_script")
    @patch("app.pipeline.pipeline.step02_assets")
    @patch("app.pipeline.pipeline.step03_tts")
    @patch("app.pipeline.pipeline.step04_subtitle")
    @patch("app.pipeline.pipeline.step05_video")
    @patch("app.pipeline.pipeline.step06_thumbnail")
    @patch("app.pipeline.pipeline.step07_quality")
    def test_pipeline_survives_regeneration_service_failure(
        self,
        mock_step07,
        mock_step06,
        mock_step05,
        mock_step04,
        mock_step03,
        mock_step02_assets,
        mock_step01,
        mock_visual_consistency,
        mock_regeneration_service,
    ):
        mock_step01.run.return_value = dict(SAMPLE_DATA)
        mock_visual_consistency.apply_visual_consistency.return_value = STYLED_SCENES
        mock_step02_assets.collect_assets.return_value = ENRICHED_SCENES
        mock_regeneration_service.run.side_effect = Exception("regen boom")

        result = pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
        )

        self.assertEqual(result["scenes"], ENRICHED_SCENES)

    @patch("app.pipeline.pipeline.regeneration_service")
    @patch("app.pipeline.pipeline.visual_consistency_engine")
    @patch("app.pipeline.pipeline.step01_script")
    @patch("app.pipeline.pipeline.step02_assets")
    @patch("app.pipeline.pipeline.step03_tts")
    @patch("app.pipeline.pipeline.step04_subtitle")
    @patch("app.pipeline.pipeline.step05_video")
    @patch("app.pipeline.pipeline.step06_thumbnail")
    @patch("app.pipeline.pipeline.step07_quality")
    def test_visual_consistency_applied_before_asset_collection(
        self,
        mock_step07,
        mock_step06,
        mock_step05,
        mock_step04,
        mock_step03,
        mock_step02_assets,
        mock_step01,
        mock_visual_consistency,
        mock_regeneration_service,
    ):
        call_order = []
        mock_step01.run.return_value = dict(SAMPLE_DATA)
        mock_visual_consistency.apply_visual_consistency.side_effect = (
            lambda scenes, channel: call_order.append("style") or STYLED_SCENES
        )
        mock_step02_assets.collect_assets.side_effect = (
            lambda scenes, path, channel: call_order.append("assets") or ENRICHED_SCENES
        )

        pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
        )

        self.assertEqual(call_order, ["style", "assets"])


if __name__ == "__main__":
    unittest.main()
