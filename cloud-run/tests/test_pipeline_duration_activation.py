"""
Sprint94 (RED) - Pipeline이 ProductionProfile.duration_target을 실제
Duration Gate/Optimizer로 전달(Activation)하는지 검증.

Sprint93까지는 data["production_profile"]을 관찰용으로만 저장했다
(step01_script.run() 실행 이후에 계산되어 Duration Gate에는 닿지
않았음). Sprint94는 이 계산을 step01_script.run() 호출 이전으로
옮기고, 얻은 duration_target(및 ±2초 tolerance로 계산한 min/max)을
step01_script.run()/step03_tts.run()의 새 optional 파라미터
(target_duration/min_acceptable/max_acceptable, target_duration/
tolerance)로 그대로 전달한다. `config.ENABLE_PRODUCTION_PROFILE`
(Sprint93, 기본 False)이 꺼져 있으면 지금까지처럼 이 파라미터들을
아예 넘기지 않아 기존 Pipeline과 완전히 동일하다.

run_pipeline()에는 이번 Sprint에서 optional 파라미터
`production_profile_name=None`이 추가된다 - 실제 운영 호출부
(factory_service.generate_short_video)는 이 값을 넘기지 않으므로
None -> "development"(45초)로, 오늘 시점 실제 운영 동작에는 영향이
없다("upload" 활성화는 Sprint95 이후 단계적으로 진행). 별도 Wrapper
클래스는 만들지 않는다 - production_profile_integration을 직접
호출한다. 아직 구현이 없으므로(RED) 모든 테스트는 실패해야 정상이다.
"""

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

from app import config
from app.pipeline import pipeline


SAMPLE_DATA = {
    "title": "t",
    "hook": "h",
    "script": "s",
    "scenes": [
        {"scene": 1, "narration": "n1", "image_prompt": "p1"},
    ],
}

STYLED_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1 styled"},
]

ENRICHED_SCENES = [
    {
        "scene": 1, "narration": "n1", "image_prompt": "p1 styled",
        "asset_path": "images/scene1.png", "provider": "ai_image",
        "asset_type": "image", "search_query": "q1", "confidence": 1.0,
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
    mocks["scene_planner"].apply_visual_type.side_effect = lambda scenes: scenes
    mocks["step02_assets"].collect_assets.return_value = ENRICHED_SCENES


class TestPipelineDurationActivation(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def _run_pipeline(self, production_profile_name=None):
        return pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
            production_profile_name=production_profile_name,
        )

    def test_flag_off_step01_called_without_duration_kwargs(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

            _, kwargs = m["step01"].run.call_args
            self.assertNotIn("target_duration", kwargs)
            self.assertNotIn("min_acceptable", kwargs)
            self.assertNotIn("max_acceptable", kwargs)

    def test_flag_off_step03_called_without_duration_kwargs(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

            _, kwargs = m["step03"].run.call_args
            self.assertNotIn("target_duration", kwargs)
            self.assertNotIn("tolerance", kwargs)

    def test_flag_on_development_profile_step01_receives_45_target(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)

            self._run_pipeline()

            _, kwargs = m["step01"].run.call_args
            self.assertEqual(kwargs.get("target_duration"), 45)
            self.assertEqual(kwargs.get("min_acceptable"), 43)
            self.assertEqual(kwargs.get("max_acceptable"), 47)

    def test_flag_on_development_profile_step03_receives_45_target_and_tolerance_2(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)

            self._run_pipeline()

            _, kwargs = m["step03"].run.call_args
            self.assertEqual(kwargs.get("target_duration"), 45)
            self.assertEqual(kwargs.get("tolerance"), 2)

    def test_flag_on_upload_profile_step01_receives_55_target(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)

            self._run_pipeline(production_profile_name="upload")

            _, kwargs = m["step01"].run.call_args
            self.assertEqual(kwargs.get("target_duration"), 55)
            self.assertEqual(kwargs.get("min_acceptable"), 53)
            self.assertEqual(kwargs.get("max_acceptable"), 57)

    def test_flag_on_upload_profile_step03_receives_55_target_and_tolerance_2(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)

            self._run_pipeline(production_profile_name="upload")

            _, kwargs = m["step03"].run.call_args
            self.assertEqual(kwargs.get("target_duration"), 55)
            self.assertEqual(kwargs.get("tolerance"), 2)


if __name__ == "__main__":
    unittest.main()
