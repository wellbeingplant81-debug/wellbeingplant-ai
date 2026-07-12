"""
Sprint95 (RED) - Pipeline이 ProductionProfile.tts_provider를 Step03까지
전달(Activation)하는지 검증.

Sprint94에서 이미 step01_script.run()보다 먼저 계산해 둔 active_profile
에서 tts_provider를 추가로 꺼내 step03_tts.run()에 전달한다. 이번
Sprint의 성공 기준은 "값이 정확히 전달되는가"이다 - 전달된 값을 받은
tts_provider.py가 내부적으로 어떤 엔진으로 라우팅하는지는 구현
세부사항으로 취급하고 이 테스트에서는 검증하지 않는다(그건
test_tts_provider_override.py의 책임). `config.ENABLE_PRODUCTION_PROFILE`
(Sprint93, 기본 False)이 꺼져 있으면 지금까지처럼 tts_provider 인자를
아예 넘기지 않는다. 아직 구현이 없으므로(RED) 모든 override 관련
테스트는 실패해야 정상이다.
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


class TestPipelineTtsProviderActivation(unittest.TestCase):

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

    def test_flag_off_step03_called_without_tts_provider_kwarg(self):
        with patched_pipeline() as m:
            _wire_defaults(m)

            self._run_pipeline()

            _, kwargs = m["step03"].run.call_args
            self.assertNotIn("tts_provider", kwargs)

    def test_flag_on_development_profile_passes_chirp_to_step03(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)

            self._run_pipeline()

            _, kwargs = m["step03"].run.call_args
            self.assertEqual(kwargs.get("tts_provider"), "chirp")

    def test_flag_on_upload_profile_passes_elevenlabs_to_step03(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", True):
            _wire_defaults(m)

            self._run_pipeline(production_profile_name="upload")

            _, kwargs = m["step03"].run.call_args
            self.assertEqual(kwargs.get("tts_provider"), "elevenlabs")


if __name__ == "__main__":
    unittest.main()
