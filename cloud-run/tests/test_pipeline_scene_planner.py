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

FAKE_SCENE_PLAN = [
    {"scene_id": 1, "purpose": "hook", "visual_type": "photo_realistic",
     "camera": "close_up", "transition": "fade", "duration": 3.0, "keywords": ["k1"]},
    {"scene_id": 2, "purpose": "cta", "visual_type": "photo_realistic",
     "camera": "medium_shot", "transition": "cross_dissolve", "duration": 3.0, "keywords": ["k2"]},
]


@contextlib.contextmanager
def patched_pipeline():
    """
    pipeline.run_pipeline()이 사용하는 모든 step/service 모듈을 patch하고,
    이름으로 접근 가능한 mock dict를 돌려줍니다. 결정적 순서에 의존하는
    스택형 @patch 데코레이터 대신 with 블록을 써서, patch 대상이 늘어나도
    인자 순서를 손으로 맞출 필요가 없게 했습니다.
    """

    with patch("app.pipeline.pipeline.step01_script") as step01, \
         patch("app.pipeline.pipeline.step02_assets") as step02_assets, \
         patch("app.pipeline.pipeline.step03_tts") as step03, \
         patch("app.pipeline.pipeline.step04_subtitle") as step04, \
         patch("app.pipeline.pipeline.step05_video") as step05, \
         patch("app.pipeline.pipeline.step06_thumbnail") as step06, \
         patch("app.pipeline.pipeline.step07_quality") as step07, \
         patch("app.pipeline.pipeline.regeneration_service") as regeneration_service, \
         patch("app.pipeline.pipeline.visual_consistency_engine") as visual_consistency, \
         patch("app.pipeline.pipeline.scene_planner_service") as scene_planner:

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
        }


def _wire_defaults(mocks):
    mocks["step01"].run.return_value = dict(SAMPLE_DATA)
    mocks["visual_consistency"].apply_visual_consistency.return_value = STYLED_SCENES
    mocks["step02_assets"].collect_assets.return_value = ENRICHED_SCENES


class TestScenePlannerFeatureFlag(unittest.TestCase):

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

            m["scene_planner"].plan_scenes.assert_not_called()
            self.assertNotIn("scene_plan", result)

    def test_planner_on_is_called_and_result_stored_on_scene_plan(self):
        # data는 pipeline 실행 내내 같은 dict 객체이므로(뒤에서
        # data["scenes"]/data["scene_plan"]이 계속 재할당됨), call_args로
        # 사후 조회하면 마지막 상태만 보인다 - 호출 시점 스냅샷을 직접
        # 캡처해야 "호출 당시 실제로 넘어온 scenes"를 검증할 수 있다.
        captured = []

        def _capture(script):
            captured.append(dict(script))
            return FAKE_SCENE_PLAN

        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_SCENE_PLANNER", True):
            _wire_defaults(m)
            m["scene_planner"].plan_scenes.side_effect = _capture

            result = self._run_pipeline()

            m["scene_planner"].plan_scenes.assert_called_once()
            self.assertEqual(captured[0]["scenes"], SAMPLE_DATA["scenes"])
            self.assertEqual(result["scene_plan"], FAKE_SCENE_PLAN)

    def test_planner_exception_does_not_break_pipeline(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_SCENE_PLANNER", True):
            _wire_defaults(m)
            m["scene_planner"].plan_scenes.side_effect = Exception("planner boom")

            result = self._run_pipeline()

            self.assertNotIn("scene_plan", result)
            self.assertEqual(result["scenes"], ENRICHED_SCENES)
            m["step03"].run.assert_called_once_with(ENRICHED_SCENES, self.project_path)
            m["regeneration_service"].run.assert_called_once_with(self.project_path)

    def test_planner_off_result_matches_pre_sprint45_pipeline_output(self):
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
                },
            )

    def test_scene_plan_is_persisted_to_script_json_when_enabled(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_SCENE_PLANNER", True):
            _wire_defaults(m)
            m["scene_planner"].plan_scenes.return_value = FAKE_SCENE_PLAN

            self._run_pipeline()

        script_path = os.path.join(self.project_path, "script.json")
        with open(script_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["scene_plan"], FAKE_SCENE_PLAN)

    def test_scene_plan_absent_from_script_json_when_disabled(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

        script_path = os.path.join(self.project_path, "script.json")
        with open(script_path, "r", encoding="utf-8") as f:
            saved = json.load(f)

        self.assertNotIn("scene_plan", saved)

    def test_original_scenes_unchanged_when_planner_enabled(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_SCENE_PLANNER", True):
            _wire_defaults(m)
            m["scene_planner"].plan_scenes.return_value = FAKE_SCENE_PLAN

            self._run_pipeline()

            m["visual_consistency"].apply_visual_consistency.assert_called_once_with(
                SAMPLE_DATA["scenes"], "wellbeing",
            )


if __name__ == "__main__":
    unittest.main()
