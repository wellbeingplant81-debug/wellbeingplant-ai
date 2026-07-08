import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.duration_gate import (
    MIN_ACCEPTABLE_SECONDS,
    MAX_ACCEPTABLE_SECONDS,
    MAX_ATTEMPTS,
    generate_script_within_duration,
)


def _scenes(*durations_in_chars):
    # 대략 5.3자/초에 가까운 chars_per_second를 쓰는 duration_estimator를
    # 직접 흉내내지 않고, estimate_fn 자체를 스텁으로 넘겨서 글자수와
    # 무관하게 원하는 예상 길이를 강제한다 (아래 _fake_estimate 참고).
    return [{"scene": i, "narration": f"n{i}"} for i in range(1, len(durations_in_chars) + 1)]


def _fake_generate(durations):
    """estimate_fn이 순서대로 durations를 반환하도록, 매 호출마다
    다른 result를 만들어내는 generate_fn 스텁을 만든다."""

    calls = {"count": 0}

    def _generate(topic, target_duration, scene_count):
        index = calls["count"]
        calls["count"] += 1
        return {
            "success": True,
            "data": {
                "title": "t",
                "scenes": [{"scene": 1, "narration": f"attempt{index}"}],
            },
        }

    return _generate, calls


class TestGenerateScriptWithinDuration(unittest.TestCase):

    def test_passes_on_first_attempt_when_in_range(self):
        generate_fn, calls = _fake_generate([45.0])
        estimate_fn = MagicMock(side_effect=[45.0])

        outcome = generate_script_within_duration(
            topic="topic",
            generate_fn=generate_fn,
            estimate_fn=estimate_fn,
        )

        self.assertTrue(outcome["passed"])
        self.assertEqual(outcome["attempts"], 1)
        self.assertEqual(outcome["estimated_seconds"], 45.0)
        self.assertEqual(calls["count"], 1)

    def test_boundary_values_are_accepted(self):
        for boundary in (MIN_ACCEPTABLE_SECONDS, MAX_ACCEPTABLE_SECONDS):
            generate_fn, _ = _fake_generate([boundary])
            estimate_fn = MagicMock(side_effect=[boundary])

            outcome = generate_script_within_duration(
                topic="topic",
                generate_fn=generate_fn,
                estimate_fn=estimate_fn,
            )

            self.assertTrue(outcome["passed"])

    def test_retries_when_out_of_range_then_passes(self):
        generate_fn, calls = _fake_generate([30.0, 45.5])
        estimate_fn = MagicMock(side_effect=[30.0, 45.5])

        outcome = generate_script_within_duration(
            topic="topic",
            generate_fn=generate_fn,
            estimate_fn=estimate_fn,
        )

        self.assertTrue(outcome["passed"])
        self.assertEqual(outcome["attempts"], 2)
        self.assertEqual(calls["count"], 2)

    def test_stops_after_max_attempts_and_returns_closest(self):
        generate_fn, calls = _fake_generate([30.0, 60.0, 41.0])
        estimate_fn = MagicMock(side_effect=[30.0, 60.0, 41.0])

        outcome = generate_script_within_duration(
            topic="topic",
            generate_fn=generate_fn,
            estimate_fn=estimate_fn,
            max_attempts=3,
        )

        self.assertFalse(outcome["passed"])
        self.assertEqual(outcome["attempts"], 3)
        self.assertEqual(calls["count"], 3)
        # 41.0(45와의 차이 4)이 30.0(차이 15)과 60.0(차이 15)보다 가깝다
        self.assertEqual(outcome["estimated_seconds"], 41.0)

    def test_never_exceeds_max_attempts_calls(self):
        generate_fn, calls = _fake_generate([10.0, 10.0, 10.0])
        estimate_fn = MagicMock(side_effect=[10.0, 10.0, 10.0])

        generate_script_within_duration(
            topic="topic",
            generate_fn=generate_fn,
            estimate_fn=estimate_fn,
            max_attempts=3,
        )

        self.assertEqual(calls["count"], 3)

    def test_default_max_attempts_is_reasonable(self):
        self.assertIn(MAX_ATTEMPTS, (2, 3))

    def test_result_contains_generate_fn_return_value(self):
        generate_fn, _ = _fake_generate([45.0])
        estimate_fn = MagicMock(side_effect=[45.0])

        outcome = generate_script_within_duration(
            topic="topic",
            generate_fn=generate_fn,
            estimate_fn=estimate_fn,
        )

        self.assertIn("result", outcome)
        self.assertIn("data", outcome["result"])
        self.assertIn("scenes", outcome["result"]["data"])

    def test_stops_retrying_as_soon_as_one_passes(self):
        # 두 번째 시도에서 통과하면 세 번째는 절대 호출되면 안 된다.
        generate_fn, calls = _fake_generate([20.0, 46.0, 999.0])
        estimate_fn = MagicMock(side_effect=[20.0, 46.0, 999.0])

        outcome = generate_script_within_duration(
            topic="topic",
            generate_fn=generate_fn,
            estimate_fn=estimate_fn,
            max_attempts=3,
        )

        self.assertEqual(calls["count"], 2)
        self.assertTrue(outcome["passed"])


if __name__ == "__main__":
    unittest.main()
