"""
Sprint94 (RED) - step01_script.run()의 target_duration override 전달.

step01_script.run()에 optional 파라미터 target_duration/min_acceptable/
max_acceptable을 추가한다(기본값 None). None이면 지금까지처럼
generate_script_within_duration()을 topic만으로 호출해(기존 45/43/47
기본값 그대로) 완전히 동일하게 동작하고, 값이 있으면 그대로
generate_script_within_duration()에 전달한다. 아직 구현이 없으므로
(RED) 모든 테스트는 실패해야 정상이다.
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

from app.steps import step01_script


FAKE_GATE_OUTCOME = {
    "result": {
        "success": True,
        "data": {
            "title": "t",
            "hook": "h",
            "script": "s",
            "scenes": [{"scene": 1, "narration": "n1", "image_prompt": "p1"}],
        },
    },
    "estimated_seconds": 45.0,
    "attempts": 1,
    "passed": True,
}


class TestStep01ScriptDurationOverride(unittest.TestCase):

    @patch(
        "app.steps.step01_script.generate_script_within_duration",
        return_value=FAKE_GATE_OUTCOME,
    )
    def test_no_override_omits_target_duration_kwarg(self, mock_gate):
        with tempfile.TemporaryDirectory() as tmp_dir:
            step01_script.run("topic", tmp_dir)

        _, kwargs = mock_gate.call_args
        self.assertNotIn("target_duration", kwargs)
        self.assertNotIn("min_acceptable", kwargs)
        self.assertNotIn("max_acceptable", kwargs)

    @patch(
        "app.steps.step01_script.generate_script_within_duration",
        return_value=FAKE_GATE_OUTCOME,
    )
    def test_override_passed_through_to_duration_gate(self, mock_gate):
        with tempfile.TemporaryDirectory() as tmp_dir:
            step01_script.run(
                "topic", tmp_dir,
                target_duration=55,
                min_acceptable=53.0,
                max_acceptable=57.0,
            )

        _, kwargs = mock_gate.call_args
        self.assertEqual(kwargs.get("target_duration"), 55)
        self.assertEqual(kwargs.get("min_acceptable"), 53.0)
        self.assertEqual(kwargs.get("max_acceptable"), 57.0)

    @patch(
        "app.steps.step01_script.generate_script_within_duration",
        return_value=FAKE_GATE_OUTCOME,
    )
    def test_no_tts_provider_omits_tts_provider_kwarg(self, mock_gate):
        with tempfile.TemporaryDirectory() as tmp_dir:
            step01_script.run("topic", tmp_dir)

        _, kwargs = mock_gate.call_args
        self.assertNotIn("tts_provider", kwargs)

    @patch(
        "app.steps.step01_script.generate_script_within_duration",
        return_value=FAKE_GATE_OUTCOME,
    )
    def test_tts_provider_passed_through_to_duration_gate(self, mock_gate):
        with tempfile.TemporaryDirectory() as tmp_dir:
            step01_script.run(
                "topic", tmp_dir,
                target_duration=55,
                min_acceptable=53.0,
                max_acceptable=57.0,
                tts_provider="elevenlabs",
            )

        _, kwargs = mock_gate.call_args
        self.assertEqual(kwargs.get("tts_provider"), "elevenlabs")

    @patch(
        "app.steps.step01_script.generate_script_within_duration",
        return_value=FAKE_GATE_OUTCOME,
    )
    def test_override_does_not_change_returned_data_shape(self, mock_gate):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data = step01_script.run(
                "topic", tmp_dir,
                target_duration=55,
                min_acceptable=53.0,
                max_acceptable=57.0,
            )

        self.assertEqual(data, FAKE_GATE_OUTCOME["result"]["data"])


if __name__ == "__main__":
    unittest.main()
