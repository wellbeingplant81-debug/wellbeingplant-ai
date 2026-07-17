"""
Sprint123 (GREEN) - Production Policy: render_profile=longform이면
production_profile의 tts_provider(예: development의 "chirp")보다
항상 ElevenLabs를 우선한다. Production(Script/Image/Asset/Video 생성)
시작 전에 ElevenLabs 가용성을 사전 검증하고, 실패하면 Script 생성조차
시작하지 않고 예외를 그대로 전파한다(Google로 자동 대체 없음).
Shorts(render_profile_name 미지정)는 사전 검증 자체를 호출하지 않고
tts_provider도 강제하지 않는다 - 기존 동작과 100% 동일하다.
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
    DEVELOPMENT_PROFILE,
    patched_pipeline,
    _wire_defaults,
)


class TestLongformForcesElevenLabs(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name

    def _run_pipeline(self, **kwargs):
        return pipeline.run_pipeline(
            topic="주제",
            project_path=self.project_path,
            channel="wellbeing",
            **kwargs,
        )

    @patch("app.pipeline.pipeline.elevenlabs_provider.validate_availability")
    def test_longform_calls_preflight_validation(self, mock_validate):
        mock_validate.return_value = ("voice-123", "Brandon")

        with patched_pipeline() as m:
            _wire_defaults(m)
            self._run_pipeline(render_profile_name="longform")

        mock_validate.assert_called_once()

    @patch("app.pipeline.pipeline.elevenlabs_provider.validate_availability")
    def test_longform_forces_tts_provider_on_step01_and_step03(self, mock_validate):
        mock_validate.return_value = ("voice-123", "Brandon")

        with patched_pipeline() as m:
            _wire_defaults(m)
            self._run_pipeline(render_profile_name="longform")

            _, step01_kwargs = m["step01"].run.call_args
            self.assertEqual(step01_kwargs["tts_provider"], "elevenlabs")

            _, step03_kwargs = m["step03"].run.call_args
            self.assertEqual(step03_kwargs["tts_provider"], "elevenlabs")

    @patch("app.pipeline.pipeline.elevenlabs_provider.validate_availability")
    def test_longform_overrides_development_profile_tts_provider(self, mock_validate):
        mock_validate.return_value = ("voice-123", "Brandon")

        with patched_pipeline() as m:
            _wire_defaults(m)
            m["production_profile_integration"].ProductionProfileIntegration.load_profile.return_value = (
                DEVELOPMENT_PROFILE
            )

            self._run_pipeline(
                render_profile_name="longform", production_profile_name="development",
            )

            _, step03_kwargs = m["step03"].run.call_args
            # DEVELOPMENT_PROFILE 자체는 tts_provider="chirp"지만,
            # Longform 강제 규칙이 항상 이긴다.
            self.assertEqual(step03_kwargs["tts_provider"], "elevenlabs")

    @patch("app.pipeline.pipeline.elevenlabs_provider.validate_availability")
    def test_preflight_failure_stops_before_script_generation(self, mock_validate):
        mock_validate.side_effect = Exception("ELEVENLABS_API_KEY 환경변수가 설정되어 있지 않습니다.")

        with patched_pipeline() as m:
            _wire_defaults(m)

            with self.assertRaises(Exception):
                self._run_pipeline(render_profile_name="longform")

            m["step01"].run.assert_not_called()

    @patch("app.pipeline.pipeline.elevenlabs_provider.validate_availability")
    def test_shorts_never_calls_preflight_validation(self, mock_validate):
        with patched_pipeline() as m:
            _wire_defaults(m)
            self._run_pipeline()

        mock_validate.assert_not_called()

    @patch("app.pipeline.pipeline.elevenlabs_provider.validate_availability")
    def test_shorts_does_not_force_tts_provider(self, mock_validate):
        with patched_pipeline() as m:
            _wire_defaults(m)
            self._run_pipeline()

            _, step01_kwargs = m["step01"].run.call_args
            self.assertNotIn("tts_provider", step01_kwargs)

            _, step03_kwargs = m["step03"].run.call_args
            self.assertNotIn("tts_provider", step03_kwargs)


if __name__ == "__main__":
    unittest.main()
