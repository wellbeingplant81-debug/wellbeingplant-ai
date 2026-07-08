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


class TestStep01ScriptUsesDurationGate(unittest.TestCase):

    @patch(
        "app.steps.step01_script.generate_script_within_duration",
        return_value=FAKE_GATE_OUTCOME,
    )
    def test_calls_duration_gate_with_topic(self, mock_gate):
        with tempfile.TemporaryDirectory() as tmp_dir:
            step01_script.run("밤에 화장실 자주 가는 이유", tmp_dir)

        args, kwargs = mock_gate.call_args
        self.assertEqual(kwargs.get("topic") or args[0], "밤에 화장실 자주 가는 이유")

    @patch(
        "app.steps.step01_script.generate_script_within_duration",
        return_value=FAKE_GATE_OUTCOME,
    )
    def test_writes_gate_result_data_to_script_json(self, mock_gate):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data = step01_script.run("topic", tmp_dir)

            self.assertEqual(data, FAKE_GATE_OUTCOME["result"]["data"])

            script_path = os.path.join(tmp_dir, "script.json")
            self.assertTrue(os.path.exists(script_path))

    @patch(
        "app.steps.step01_script.generate_script_within_duration",
        return_value=FAKE_GATE_OUTCOME,
    )
    def test_returns_scenes_from_gate_result(self, mock_gate):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data = step01_script.run("topic", tmp_dir)

        self.assertEqual(len(data["scenes"]), 1)
        self.assertEqual(data["scenes"][0]["narration"], "n1")


if __name__ == "__main__":
    unittest.main()
