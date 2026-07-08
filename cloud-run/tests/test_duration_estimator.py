import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.duration_estimator import (
    DEFAULT_CHARS_PER_SECOND,
    SENTENCE_PAUSE_SECONDS,
    COMMA_PAUSE_SECONDS,
    TARGET_DURATION_SECONDS,
    estimate_duration,
    estimate_script_duration,
    duration_deviation,
)


class TestEstimateDurationBasics(unittest.TestCase):

    def test_empty_string_returns_zero(self):
        self.assertEqual(estimate_duration(""), 0.0)

    def test_none_returns_zero(self):
        self.assertEqual(estimate_duration(None), 0.0)

    def test_short_text_matches_formula(self):
        text = "오늘부터 물을 줄이세요"
        expected = len(text.replace(" ", "")) / DEFAULT_CHARS_PER_SECOND
        self.assertAlmostEqual(estimate_duration(text), expected, places=3)


class TestEstimateDurationScalesWithLength(unittest.TestCase):

    def test_long_text_takes_longer_than_short_text(self):
        short_text = "물을 줄이세요."
        long_text = (
            "밤에 깨서 화장실 가는 진짜 이유는 나이가 아니라 저녁에 먹는 "
            "짠 음식 때문일 수 있습니다. 오늘 저녁 국물을 반만 드시고 "
            "짠 반찬을 하나만 줄여보세요."
        )
        self.assertGreater(
            estimate_duration(long_text),
            estimate_duration(short_text),
        )

    def test_duration_roughly_proportional_to_char_count(self):
        base = "안녕하세요 반갑습니다"
        doubled = base + " " + base
        self.assertAlmostEqual(
            estimate_duration(doubled),
            estimate_duration(base) * 2,
            places=3,
        )


class TestEstimateDurationWithNumbers(unittest.TestCase):

    def test_number_with_unit_is_expanded_before_counting(self):
        # "2번" -> "두 번"으로 정규화된 뒤 글자수가 계산되어야 한다
        # (speech_normalizer와 동일한 정규화 규칙을 내부적으로 사용).
        with_unit = estimate_duration("밤에 2번 깨요")
        manually_normalized = estimate_duration("밤에 두 번 깨요")
        self.assertAlmostEqual(with_unit, manually_normalized, places=3)

    def test_number_with_unit_takes_longer_than_raw_digit_would_suggest(self):
        # "21번"은 원문 3글자(2,1,번)지만 실제 발화("스물한 번")는
        # 4글자(스,물,한,번) 분량이므로, 단순 원문 글자수 기반 추정보다
        # 더 길게 나와야 한다.
        naive_estimate = len("21번") / DEFAULT_CHARS_PER_SECOND
        actual_estimate = estimate_duration("21번")
        self.assertGreater(actual_estimate, naive_estimate)


class TestEstimateDurationWithPunctuation(unittest.TestCase):

    def test_sentence_boundary_adds_pause(self):
        without_period = estimate_duration("오늘부터 물을 줄이세요")
        with_period = estimate_duration("오늘부터 물을 줄이세요.")
        self.assertAlmostEqual(
            with_period - without_period,
            SENTENCE_PAUSE_SECONDS,
            places=3,
        )

    def test_comma_adds_smaller_pause_than_sentence_boundary(self):
        with_comma = estimate_duration("첫째, 둘째입니다")
        with_period = estimate_duration("첫째. 둘째입니다")
        self.assertLess(
            with_comma - estimate_duration("첫째 둘째입니다"),
            with_period - estimate_duration("첫째 둘째입니다"),
        )

    def test_comma_pause_matches_constant(self):
        without_comma = estimate_duration("첫째 둘째입니다")
        with_comma = estimate_duration("첫째, 둘째입니다")
        self.assertAlmostEqual(
            with_comma - without_comma,
            COMMA_PAUSE_SECONDS,
            places=3,
        )


class TestEstimateScriptDuration(unittest.TestCase):

    def test_sums_all_scene_narrations(self):
        scenes = [
            {"scene": 1, "narration": "밤에 자주 깨시나요?"},
            {"scene": 2, "narration": "짠 음식이 원인일 수 있습니다."},
        ]
        expected = sum(
            estimate_duration(scene["narration"]) for scene in scenes
        )
        self.assertAlmostEqual(
            estimate_script_duration(scenes),
            expected,
            places=3,
        )

    def test_empty_scene_list_returns_zero(self):
        self.assertEqual(estimate_script_duration([]), 0.0)


class TestDurationDeviation(unittest.TestCase):

    def test_deviation_is_positive_when_over_target(self):
        self.assertAlmostEqual(
            duration_deviation(50.0, target=TARGET_DURATION_SECONDS),
            50.0 - TARGET_DURATION_SECONDS,
            places=3,
        )

    def test_deviation_is_negative_when_under_target(self):
        self.assertAlmostEqual(
            duration_deviation(40.0, target=TARGET_DURATION_SECONDS),
            40.0 - TARGET_DURATION_SECONDS,
            places=3,
        )

    def test_deviation_defaults_to_45_second_target(self):
        self.assertEqual(TARGET_DURATION_SECONDS, 45.0)
        self.assertAlmostEqual(duration_deviation(45.0), 0.0, places=3)


class TestCalibrationAgainstRealAudio(unittest.TestCase):
    """
    Sprint53-1 보정 근거: 실제로 생성된 프로젝트(output/20260707_161744,
    output/20260706_164907, Google TTS ko-KR-Chirp3-HD-Aoede)의 script.json
    narration과, 그 결과물 audio/voice.mp3를 ffprobe로 측정한 실제 길이를
    그대로 하드코딩한 회귀 테스트. output/는 .gitignore 대상이라 CI에서도
    재현 가능하도록 값을 직접 박아 넣는다.

    개별 scene 150개 표본 기준 평균 절대오차는 약 0.4초(약 6%),
    영상 전체(48개) 기준 평균 절대오차는 약 1.56초(약 3.6%)였다.
    두 표본 모두 이보다 넉넉한 허용치인 ±3초 이내여야 한다.
    """

    TOLERANCE_SECONDS = 3.0

    def test_matches_real_video_20260706_164907(self):
        scenes = [
            {"narration": "혹시 아침에 일어나자마자 찬물부터 찾으시나요? 당신의 몸이 보내는 경고 신호, 놓치고 있을 수 있습니다."},
            {"narration": "사실 빈속에 마시는 차가운 물은 위장에 큰 부담을 줘서 소화 기능을 떨어뜨릴 수 있어요."},
            {"narration": "진짜 보약이 되는 물은 바로 '미지근한 물'입니다. 체온과 비슷한 온도의 물이 가장 이상적이죠."},
            {"narration": "이 미지근한 물 한 잔이 밤새 잠자던 우리 몸의 장기들을 부드럽게 깨우고 신진대사를 활발하게 만들어 줍니다."},
            {"narration": "여기에 비타민C가 풍부한 레몬 한 조각을 더하면, 독소 배출과 피부 미용 효과까지 볼 수 있어요."},
            {"narration": "오늘부터 이 간단한 습관 하나로, 매일 아침을 세상에서 가장 건강하게 시작해 보세요!"},
        ]
        actual_seconds = 43.65  # ffprobe로 측정한 audio/voice.mp3 실제 길이

        estimated = estimate_script_duration(scenes)

        self.assertLessEqual(
            abs(estimated - actual_seconds),
            self.TOLERANCE_SECONDS,
        )

    def test_matches_real_video_20260707_161744(self):
        scenes = [
            {"narration": "밤에 깨서 화장실 가는 진짜 이유, 대부분 '이것' 때문입니다."},
            {"narration": "혹시 밤에 2번 이상 깨신다면, 나이나 물 마시는 습관만 탓하고 계셨나요?"},
            {"narration": "놀랍게도 진짜 범인은 저녁 식사에 숨어있던 '소금'일 수 있습니다."},
            {"narration": "짠 음식은 낮 동안 몸에 수분을 가뒀다가, 우리가 잠든 밤에 한꺼번에 배출시키거든요."},
            {"narration": "해결책은 의외로 간단합니다. 오늘 저녁 국물은 반만 드시고, 짠 반찬 하나만 줄여보세요."},
            {"narration": "이 작은 습관 하나가 통잠의 시작입니다. 도움이 되셨다면 저장하고 꼭 실천해보세요."},
        ]
        actual_seconds = 35.98  # ffprobe로 측정한 audio/voice.mp3 실제 길이

        estimated = estimate_script_duration(scenes)

        self.assertLessEqual(
            abs(estimated - actual_seconds),
            self.TOLERANCE_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
