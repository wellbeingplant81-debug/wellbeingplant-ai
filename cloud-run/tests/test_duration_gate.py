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
    _build_retry_feedback,
    generate_script_within_duration,
)
from app.services.duration_estimator import (
    DEFAULT_CHARS_PER_SECOND,
    ELEVENLABS_CHARS_PER_SECOND,
)


def _scenes(*durations_in_chars):
    # 대략 5.3자/초에 가까운 chars_per_second를 쓰는 duration_estimator를
    # 직접 흉내내지 않고, estimate_fn 자체를 스텁으로 넘겨서 글자수와
    # 무관하게 원하는 예상 길이를 강제한다 (아래 _fake_estimate 참고).
    return [{"scene": i, "narration": f"n{i}"} for i in range(1, len(durations_in_chars) + 1)]


def _fake_generate(durations):
    """estimate_fn이 순서대로 durations를 반환하도록, 매 호출마다
    다른 result를 만들어내는 generate_fn 스텁을 만든다. Sprint69-2 -
    각 호출에 실제로 전달된 kwargs(특히 retry_feedback)를 calls["kwargs"]에
    기록해, 적응형 재시도 피드백이 제대로 전달되는지 검증할 수 있게 한다."""

    calls = {"count": 0, "kwargs": []}

    def _generate(topic, target_duration, scene_count, retry_feedback="", chars_per_second=None):
        index = calls["count"]
        calls["count"] += 1
        calls["kwargs"].append({
            "topic": topic,
            "target_duration": target_duration,
            "scene_count": scene_count,
            "retry_feedback": retry_feedback,
            "chars_per_second": chars_per_second,
        })
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


class TestBuildRetryFeedback(unittest.TestCase):
    """Sprint69-2 - estimated_seconds를 기반으로 부족/초과 글자 수를
    계산해 다음 Writer 시도에 줄 구체적 피드백 문구를 만든다."""

    def test_too_short_asks_for_more_chars(self):
        feedback = _build_retry_feedback(
            estimated_seconds=38.16, target_duration=45,
            chars_per_second=DEFAULT_CHARS_PER_SECOND,
        )
        expected_chars = round((45 - 38.16) * DEFAULT_CHARS_PER_SECOND)

        self.assertIn("더 길게", feedback)
        self.assertIn(str(expected_chars), feedback)
        self.assertIn("38.2", feedback)

    def test_too_long_asks_for_fewer_chars(self):
        feedback = _build_retry_feedback(
            estimated_seconds=52.0, target_duration=45,
            chars_per_second=DEFAULT_CHARS_PER_SECOND,
        )
        expected_chars = round((52.0 - 45) * DEFAULT_CHARS_PER_SECOND)

        self.assertIn("더 짧게", feedback)
        self.assertIn(str(expected_chars), feedback)

    def test_feedback_scales_with_shortfall_size(self):
        small_gap = _build_retry_feedback(44.0, 45, DEFAULT_CHARS_PER_SECOND)
        large_gap = _build_retry_feedback(20.0, 45, DEFAULT_CHARS_PER_SECOND)

        small_chars = round((45 - 44.0) * DEFAULT_CHARS_PER_SECOND)
        large_chars = round((45 - 20.0) * DEFAULT_CHARS_PER_SECOND)

        self.assertIn(str(small_chars), small_gap)
        self.assertIn(str(large_chars), large_gap)
        self.assertNotEqual(small_chars, large_chars)


class TestAdaptiveRetryFeedbackThreading(unittest.TestCase):
    """Sprint69-2 - 재시도할 때 직전 시도의 estimated_seconds 기반
    피드백이 다음 generate_fn 호출로 실제 전달되는지 검증한다."""

    def test_first_attempt_has_no_retry_feedback(self):
        generate_fn, calls = _fake_generate([30.0, 45.0])
        estimate_fn = MagicMock(side_effect=[30.0, 45.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
        )

        self.assertEqual(calls["kwargs"][0]["retry_feedback"], "")

    def test_second_attempt_receives_feedback_based_on_first_estimate(self):
        generate_fn, calls = _fake_generate([30.0, 45.0])
        estimate_fn = MagicMock(side_effect=[30.0, 45.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
        )

        second_feedback = calls["kwargs"][1]["retry_feedback"]
        self.assertNotEqual(second_feedback, "")
        self.assertIn("더 길게", second_feedback)

    def test_third_attempt_uses_most_recent_estimate_not_first(self):
        # 2번째 시도(60.0, 너무 김)가 1번째(30.0, 너무 짧음)보다 최신이므로
        # 3번째 호출의 피드백은 "더 짧게"(60.0 기준)여야 한다.
        generate_fn, calls = _fake_generate([30.0, 60.0, 41.0])
        estimate_fn = MagicMock(side_effect=[30.0, 60.0, 41.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
            max_attempts=3,
        )

        third_feedback = calls["kwargs"][2]["retry_feedback"]
        self.assertIn("더 짧게", third_feedback)

    def test_passing_first_try_never_builds_feedback(self):
        generate_fn, calls = _fake_generate([45.0])
        estimate_fn = MagicMock(side_effect=[45.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
        )

        self.assertEqual(calls["kwargs"][0]["retry_feedback"], "")


class TestShortfallSecondsInOutcome(unittest.TestCase):
    """Sprint69-2 - QA 로그에 부족 시간을 명확히 기록하기 위해,
    outcome에 target 대비 shortfall_seconds(양수=부족, 음수=초과)를
    포함한다."""

    def test_shortfall_seconds_present_when_passed(self):
        generate_fn, _ = _fake_generate([45.0])
        estimate_fn = MagicMock(side_effect=[45.0])

        outcome = generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
        )

        self.assertIn("shortfall_seconds", outcome)
        self.assertAlmostEqual(outcome["shortfall_seconds"], 0.0, places=3)

    def test_shortfall_seconds_reflects_gap_after_all_attempts_fail(self):
        generate_fn, _ = _fake_generate([30.0, 60.0, 41.0])
        estimate_fn = MagicMock(side_effect=[30.0, 60.0, 41.0])

        outcome = generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
            max_attempts=3,
        )

        # target(45)과 최종 채택된 41.0의 차이 = 4.0(부족)
        self.assertFalse(outcome["passed"])
        self.assertAlmostEqual(outcome["shortfall_seconds"], 4.0, places=3)

    def test_shortfall_seconds_negative_when_estimate_too_long(self):
        generate_fn, _ = _fake_generate([60.0, 60.0, 60.0])
        estimate_fn = MagicMock(side_effect=[60.0, 60.0, 60.0])

        outcome = generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
            max_attempts=3,
        )

        self.assertAlmostEqual(outcome["shortfall_seconds"], -15.0, places=3)


class TestProviderAwareCharsPerSecond(unittest.TestCase):
    """Sprint97 - tts_provider가 주어지면 estimate_fn/generate_fn/재시도
    피드백 모두 그 provider에 맞는 chars_per_second(duration_estimator.
    chars_per_second_for_provider)를 써야 한다. 주어지지 않으면(기본값
    None) 기존과 동일하게 DEFAULT_CHARS_PER_SECOND(Chirp)를 쓴다."""

    def test_no_tts_provider_uses_default_chars_per_second_for_estimate(self):
        generate_fn, _ = _fake_generate([45.0])
        estimate_fn = MagicMock(side_effect=[45.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
        )

        _, kwargs = estimate_fn.call_args
        self.assertEqual(kwargs.get("chars_per_second"), DEFAULT_CHARS_PER_SECOND)

    def test_elevenlabs_tts_provider_uses_elevenlabs_chars_per_second_for_estimate(self):
        generate_fn, _ = _fake_generate([45.0])
        estimate_fn = MagicMock(side_effect=[45.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
            tts_provider="elevenlabs",
        )

        _, kwargs = estimate_fn.call_args
        self.assertEqual(kwargs.get("chars_per_second"), ELEVENLABS_CHARS_PER_SECOND)

    def test_elevenlabs_tts_provider_reaches_generate_fn(self):
        generate_fn, calls = _fake_generate([45.0])
        estimate_fn = MagicMock(side_effect=[45.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
            tts_provider="elevenlabs",
        )

        self.assertEqual(calls["kwargs"][0]["chars_per_second"], ELEVENLABS_CHARS_PER_SECOND)

    def test_chirp_tts_provider_uses_default_chars_per_second(self):
        generate_fn, calls = _fake_generate([45.0])
        estimate_fn = MagicMock(side_effect=[45.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
            tts_provider="chirp",
        )

        self.assertEqual(calls["kwargs"][0]["chars_per_second"], DEFAULT_CHARS_PER_SECOND)

    def test_retry_feedback_uses_elevenlabs_chars_per_second(self):
        generate_fn, calls = _fake_generate([30.0, 45.0])
        estimate_fn = MagicMock(side_effect=[30.0, 45.0])

        generate_script_within_duration(
            topic="topic", generate_fn=generate_fn, estimate_fn=estimate_fn,
            tts_provider="elevenlabs",
        )

        # target_duration 기본값(45, generate_script_within_duration의
        # target_duration 파라미터 - Writer 프롬프트 목표) 기준.
        expected_chars = round((45 - 30.0) * ELEVENLABS_CHARS_PER_SECOND)
        self.assertIn(str(expected_chars), calls["kwargs"][1]["retry_feedback"])


if __name__ == "__main__":
    unittest.main()
