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

VISUAL_TYPED_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1 styled", "visual_type": "real"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2 styled", "visual_type": "ai"},
]

ENRICHED_SCENES = [
    {
        "scene": 1, "narration": "n1", "image_prompt": "p1 styled",
        "visual_type": "real",
        "asset_path": "images/scene1.png", "provider": "pexels_image",
        "asset_type": "image", "search_query": "q1", "confidence": 0.8,
    },
    {
        "scene": 2, "narration": "n2", "image_prompt": "p2 styled",
        "visual_type": "ai",
        "asset_path": "images/scene2.png", "provider": "ai_image",
        "asset_type": "image", "search_query": "q2", "confidence": 1.0,
    },
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
            "thumbnail_headline_service": thumbnail_headline_service,
        }


def _wire_defaults(mocks):
    mocks["step01"].run.return_value = dict(SAMPLE_DATA)
    mocks["visual_consistency"].apply_visual_consistency.return_value = STYLED_SCENES
    mocks["scene_planner"].apply_visual_type.return_value = VISUAL_TYPED_SCENES
    mocks["step02_assets"].collect_assets.return_value = ENRICHED_SCENES


class TestPipelineAppliesVisualType(unittest.TestCase):

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

    def test_apply_visual_type_called_with_scenes_after_visual_consistency(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

            m["scene_planner"].apply_visual_type.assert_called_once_with(
                STYLED_SCENES,
            )

    def test_apply_visual_type_output_feeds_into_collect_assets(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

            m["step02_assets"].collect_assets.assert_called_once_with(
                VISUAL_TYPED_SCENES, self.project_path, "wellbeing",
            )

    def test_apply_visual_type_runs_regardless_of_scene_planner_flag(self):
        # scene_plan(ENABLE_SCENE_PLANNER)은 기본적으로 꺼져 있는 optional
        # 오버레이지만, visual_type 분기는 실제 asset 선택에 직접
        # 쓰이는 필수 기능이므로 그 플래그와 무관하게 항상 호출돼야 한다.
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_SCENE_PLANNER", False):
            _wire_defaults(m)

            self._run_pipeline()

            m["scene_planner"].apply_visual_type.assert_called_once()

    def test_final_scenes_include_visual_type_field(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            result = self._run_pipeline()

            self.assertEqual(result["scenes"], ENRICHED_SCENES)
            for scene in result["scenes"]:
                self.assertIn("visual_type", scene)


if __name__ == "__main__":
    unittest.main()
