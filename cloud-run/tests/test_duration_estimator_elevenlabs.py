"""
Sprint97 (RED) - Duration Estimator에 tts_provider별 chars_per_second
계수를 추가한다.

Production QA(output/20260713_084207, upload profile)에서 발견된 버그:
Duration Gate/script_service가 항상 Chirp 계수(DEFAULT_CHARS_PER_SECOND=
5.93)로 narration 길이를 추정해, 실제로 더 느리게 말하는 ElevenLabs
(upload profile의 tts_provider)에서는 목표(55±2초)보다 훨씬 긴 실제
오디오(68.68초)가 나왔다. chars_per_second_for_provider()가 tts_provider
값("chirp"/"elevenlabs" - ProductionProfile과 동일한 문자열)에 맞는
계수를 고르게 한다. 아직 구현이 없으므로(RED) 모든 테스트는 실패해야
정상이다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.duration_estimator import (
    DEFAULT_CHARS_PER_SECOND,
    ELEVENLABS_CHARS_PER_SECOND,
    chars_per_second_for_provider,
)


class TestElevenLabsCharsPerSecondConstant(unittest.TestCase):

    def test_elevenlabs_constant_differs_from_default(self):
        self.assertNotEqual(ELEVENLABS_CHARS_PER_SECOND, DEFAULT_CHARS_PER_SECOND)

    def test_elevenlabs_constant_is_slower_than_chirp(self):
        # 2026-07-13 실측: ElevenLabs가 Chirp보다 느리게 말한다.
        self.assertLess(ELEVENLABS_CHARS_PER_SECOND, DEFAULT_CHARS_PER_SECOND)


class TestCharsPerSecondForProvider(unittest.TestCase):

    def test_none_returns_default(self):
        self.assertEqual(chars_per_second_for_provider(None), DEFAULT_CHARS_PER_SECOND)

    def test_no_arg_returns_default(self):
        self.assertEqual(chars_per_second_for_provider(), DEFAULT_CHARS_PER_SECOND)

    def test_chirp_returns_default(self):
        self.assertEqual(chars_per_second_for_provider("chirp"), DEFAULT_CHARS_PER_SECOND)

    def test_elevenlabs_returns_elevenlabs_constant(self):
        self.assertEqual(
            chars_per_second_for_provider("elevenlabs"), ELEVENLABS_CHARS_PER_SECOND,
        )

    def test_unknown_provider_falls_back_to_default(self):
        self.assertEqual(chars_per_second_for_provider("unknown"), DEFAULT_CHARS_PER_SECOND)


if __name__ == "__main__":
    unittest.main()
