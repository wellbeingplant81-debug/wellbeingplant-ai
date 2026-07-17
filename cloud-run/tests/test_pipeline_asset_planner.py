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

FAKE_ASSET_PLAN = {
    1: {"scene": 1, "prefer_ai": True, "visual_profile": {
        "camera_distance": "wide", "camera_angle": "eye level",
        "composition": "centered", "lighting": "soft daylight",
    }},
    2: {"scene": 2, "prefer_ai": False, "visual_profile": {
        "camera_distance": "medium", "camera_angle": "low angle",
        "composition": "rule of thirds", "lighting": "dramatic light",
    }},
}


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
         patch("app.pipeline.pipeline.asset_planner") as asset_planner, \
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
            "asset_planner": asset_planner,
            "thumbnail_headline_service": thumbnail_headline_service,
        }


def _wire_defaults(mocks):
    mocks["step01"].run.return_value = dict(SAMPLE_DATA)
    mocks["visual_consistency"].apply_visual_consistency.return_value = STYLED_SCENES
    # apply_visual_type()은 항상 실행되는 필수 분기(Sprint60)이므로,
    # 여기서 STYLED_SCENES를 그대로 통과시켜야 asset_planner가 실제로
    # 어떤 scenes를 넘겨받는지 검증할 수 있다.
    mocks["scene_planner"].apply_visual_type.side_effect = lambda scenes: scenes
    mocks["step02_assets"].collect_assets.return_value = ENRICHED_SCENES


class TestAssetPlannerFeatureFlag(unittest.TestCase):

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

    def test_planner_off_by_default_is_never_called(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            result = self._run_pipeline()

            m["asset_planner"].plan_asset_strategy.assert_not_called()
            self.assertNotIn("asset_plan", result)

    def test_planner_off_collect_assets_called_without_asset_plan_kwarg(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

            _, kwargs = m["step02_assets"].collect_assets.call_args
            self.assertIsNone(kwargs.get("asset_plan"))

    def test_planner_on_is_called_and_result_stored_on_asset_plan(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_ASSET_PLANNER", True):
            _wire_defaults(m)
            m["asset_planner"].plan_asset_strategy.return_value = FAKE_ASSET_PLAN

            result = self._run_pipeline()

            m["asset_planner"].plan_asset_strategy.assert_called_once_with(STYLED_SCENES)
            self.assertEqual(result["asset_plan"], FAKE_ASSET_PLAN)

    def test_planner_on_passes_asset_plan_to_collect_assets(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_ASSET_PLANNER", True):
            _wire_defaults(m)
            m["asset_planner"].plan_asset_strategy.return_value = FAKE_ASSET_PLAN

            self._run_pipeline()

            _, kwargs = m["step02_assets"].collect_assets.call_args
            self.assertEqual(kwargs.get("asset_plan"), FAKE_ASSET_PLAN)

    def test_planner_exception_does_not_break_pipeline(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_ASSET_PLANNER", True):
            _wire_defaults(m)
            m["asset_planner"].plan_asset_strategy.side_effect = Exception("planner boom")

            result = self._run_pipeline()

            self.assertNotIn("asset_plan", result)
            self.assertEqual(result["scenes"], ENRICHED_SCENES)
            m["step03"].run.assert_called_once_with(ENRICHED_SCENES, self.project_path)
            m["regeneration_service"].run.assert_called_once_with(self.project_path)

    def test_planner_off_result_matches_pre_sprint77_pipeline_output(self):
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

    def test_asset_plan_is_persisted_to_script_json_when_enabled(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_ASSET_PLANNER", True):
            _wire_defaults(m)
            m["asset_planner"].plan_asset_strategy.return_value = FAKE_ASSET_PLAN

            self._run_pipeline()

        script_path = os.path.join(self.project_path, "script.json")
        with open(script_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        # JSON 저장/로드를 거치면 dict 키가 문자열로 바뀐다.
        self.assertEqual(saved["asset_plan"]["1"], FAKE_ASSET_PLAN[1])

    def test_asset_plan_absent_from_script_json_when_disabled(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

        script_path = os.path.join(self.project_path, "script.json")
        with open(script_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertNotIn("asset_plan", saved)


if __name__ == "__main__":
    unittest.main()
