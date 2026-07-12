"""
Sprint93 (RED) - ProductionProfile Activation 테스트.

별도 Activation 래퍼 클래스/함수 없이, 실제 Pipeline
(app/pipeline/pipeline.py)이 ProductionProfileIntegration.load_profile()을
직접 호출하도록 준비한다. Sprint77 Asset Planner Feature Flag
(test_pipeline_asset_planner.py)와 동일한 패턴을 따른다:
`config.ENABLE_PRODUCTION_PROFILE`(기본값 False)이 꺼져 있으면
`production_profile_integration`을 아예 호출하지 않고 결과에도
`production_profile` 키를 추가하지 않아 기존 Pipeline 출력과 완전히
동일하다. 켜져 있으면 `ProductionProfileIntegration.load_profile(enabled=True)`
를 호출해 그 결과를 `data["production_profile"]`에 그대로 저장한다.
아직 구현이 없으므로(RED) 모든 테스트는 실패해야 정상이다.
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

DEVELOPMENT_PROFILE = {
    "profile": "development", "duration_target": 45,
    "tts_provider": "chirp", "asset_strategy": "default",
}

UPLOAD_PROFILE = {
    "profile": "upload", "duration_target": 55,
    "tts_provider": "elevenlabs", "asset_strategy": "upload",
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
         patch("app.pipeline.pipeline.production_profile_integration") as production_profile_integration:

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
            "production_profile_integration": production_profile_integration,
        }


def _wire_defaults(mocks):
    mocks["step01"].run.return_value = dict(SAMPLE_DATA)
    mocks["visual_consistency"].apply_visual_consistency.return_value = STYLED_SCENES
    mocks["scene_planner"].apply_visual_type.side_effect = lambda scenes: scenes
    mocks["step02_assets"].collect_assets.return_value = ENRICHED_SCENES


class TestPipelineProductionProfileFeatureFlag(unittest.TestCase):

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

    def test_feature_flag_default_off(self):
        self.assertFalse(config.ENABLE_PRODUCTION_PROFILE)

    def test_default_pipeline_behavior_unchanged(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            result = self._run_pipeline()

            m["production_profile_integration"].ProductionProfileIntegration.load_profile.assert_not_called()
            self.assertNotIn("production_profile", result)

    def test_existing_e2e_path_unchanged(self):
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

    def test_enabled_reads_production_profile(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)
            m["production_profile_integration"].ProductionProfileIntegration.load_profile.return_value = (
                DEVELOPMENT_PROFILE
            )

            result = self._run_pipeline()

            # Sprint94 - production_profile_name(기본 None) 패스스루가
            # 추가되며 profile_name 키워드 인자가 함께 전달된다.
            m["production_profile_integration"].ProductionProfileIntegration.load_profile.assert_called_once_with(
                profile_name=None,
                enabled=True,
            )
            self.assertEqual(result["production_profile"], DEVELOPMENT_PROFILE)

    def test_pipeline_uses_active_profile(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)
            m["production_profile_integration"].ProductionProfileIntegration.load_profile.return_value = (
                UPLOAD_PROFILE
            )

            result = self._run_pipeline()

            self.assertEqual(result["production_profile"]["profile"], "upload")

    def test_return_type_is_profile(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)
            m["production_profile_integration"].ProductionProfileIntegration.load_profile.return_value = (
                DEVELOPMENT_PROFILE
            )

            result = self._run_pipeline()

            self.assertIsInstance(result["production_profile"], dict)


if __name__ == "__main__":
    unittest.main()
