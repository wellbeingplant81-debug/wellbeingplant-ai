"""
Sprint100-2 - Explicit ProductionProfile Opt-In.

지금까지 ProductionProfile은 오직 전역 플래그 config.ENABLE_PRODUCTION_
PROFILE(기본 False)로만 켜졌다 - 실제 서비스 라우터(app/routers/
factory.py, batch.py)는 production_profile_name을 전혀 넘기지 않고
전역 플래그도 켜지 않아서, 실제 업로드용 영상 생성이 지금까지 한 번도
ProductionProfile(ElevenLabs/실제 BGM/실제 Asset Strategy/실제 Duration
Target)을 쓴 적이 없었다("연습(QA)만 실전, 실전은 연습" 상태).

전역 플래그를 서버 프로세스 전체에서 True로 바꾸는 것은 FastAPI가
동시에 여러 요청을 처리할 때 요청 간에 서로 영향을 주는 전역 mutable
state라 안전하지 않다. 대신 run_pipeline()이 production_profile_name을
"명시적으로" 받으면(호출자가 opt-in) 전역 플래그와 무관하게 그 요청
1건에 한해 profile을 활성화하도록 게이트 조건을 바꾼다. 전역 플래그
자체의 기본값(False)과 그 의미(아무도 opt-in하지 않으면 예전과 완전히
동일)는 전혀 바뀌지 않는다 - 기존 test_pipeline_production_profile.py의
모든 테스트가 그대로 통과해야 한다.
"""

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

from tests.test_pipeline_production_profile import (
    UPLOAD_PROFILE,
    patched_pipeline,
    _wire_defaults,
)


class TestExplicitProfileOptIn(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def test_explicit_profile_name_activates_even_when_flag_off(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", False):
            _wire_defaults(m)
            m["production_profile_integration"].ProductionProfileIntegration.load_profile.return_value = (
                UPLOAD_PROFILE
            )

            result = pipeline.run_pipeline(
                topic="주제",
                project_path=self.project_path,
                channel="wellbeing",
                production_profile_name="upload",
            )

            m["production_profile_integration"].ProductionProfileIntegration.load_profile.assert_called_once_with(
                profile_name="upload",
                enabled=True,
            )
            self.assertEqual(result["production_profile"]["profile"], "upload")

    def test_no_profile_name_and_flag_off_stays_unchanged(self):
        with patched_pipeline() as m, \
             patch("app.pipeline.pipeline.config.ENABLE_PRODUCTION_PROFILE", False):
            _wire_defaults(m)

            result = pipeline.run_pipeline(
                topic="주제",
                project_path=self.project_path,
                channel="wellbeing",
            )

            m["production_profile_integration"].ProductionProfileIntegration.load_profile.assert_not_called()
            self.assertNotIn("production_profile", result)


if __name__ == "__main__":
    unittest.main()
