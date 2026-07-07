import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.speech_normalizer import normalize_for_speech


class TestSpeechNormalizerPriorityCases(unittest.TestCase):
    """Sprint52 요구사항에 명시된 8개 우선 지원 케이스."""

    def test_1_beon_to_han_beon(self):
        self.assertEqual(normalize_for_speech("1번"), "한 번")

    def test_2_beon_to_du_beon(self):
        self.assertEqual(normalize_for_speech("2번"), "두 번")

    def test_3_myeong_to_se_myeong(self):
        self.assertEqual(normalize_for_speech("3명"), "세 명")

    def test_4_gae_to_ne_gae(self):
        self.assertEqual(normalize_for_speech("4개"), "네 개")

    def test_5_percent_to_o_percent(self):
        self.assertEqual(normalize_for_speech("5%"), "오 퍼센트")

    def test_10km_to_sip_kilometer(self):
        self.assertEqual(normalize_for_speech("10km"), "십 킬로미터")

    def test_2kg_to_i_kilogram(self):
        self.assertEqual(normalize_for_speech("2kg"), "이 킬로그램")

    def test_3_sigan_to_se_sigan(self):
        self.assertEqual(normalize_for_speech("3시간"), "세 시간")


class TestSpeechNormalizerInSentence(unittest.TestCase):

    def test_normalizes_within_full_narration(self):
        result = normalize_for_speech("밤에 2번 이상 화장실 가세요?")
        self.assertEqual(result, "밤에 두 번 이상 화장실 가세요?")

    def test_normalizes_multiple_occurrences_in_one_sentence(self):
        result = normalize_for_speech("하루에 3번, 일주일에 5%씩 늘었어요")
        self.assertEqual(result, "하루에 세 번, 일주일에 오 퍼센트씩 늘었어요")

    def test_preserves_surrounding_punctuation_and_particles(self):
        result = normalize_for_speech("2개는 버리세요.")
        self.assertEqual(result, "두 개는 버리세요.")


class TestSpeechNormalizerNoOp(unittest.TestCase):

    def test_text_without_numbers_is_unchanged(self):
        text = "오늘 저녁 식단부터 싱겁게 바꿔보세요."
        self.assertEqual(normalize_for_speech(text), text)

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(normalize_for_speech(""), "")

    def test_none_input_returns_none(self):
        self.assertIsNone(normalize_for_speech(None))

    def test_unknown_unit_is_left_untouched(self):
        text = "가격은 3달러입니다"
        self.assertEqual(normalize_for_speech(text), text)

    def test_number_without_unit_is_left_untouched(self):
        text = "숫자 123은 그대로 둡니다"
        self.assertEqual(normalize_for_speech(text), text)


class TestSpeechNormalizerDoesNotOverreach(unittest.TestCase):

    def test_does_not_match_unit_embedded_in_longer_word(self):
        # "kg짜리" 뒤에 다른 한글이 더 붙는 경우가 아니라, 단위 자체가
        # 다른 문자와 붙어 새로운 토큰을 이루는 경우까지 오매칭하지 않는다.
        text = "10kmh"
        self.assertEqual(normalize_for_speech(text), text)

    def test_original_string_not_mutated_in_place(self):
        original = "2번"
        normalize_for_speech(original)
        self.assertEqual(original, "2번")


class TestNativeVsSinoNumberSystems(unittest.TestCase):
    """번/명/개/시간은 고유어(한/두/세...), %/km/kg는 한자어(일/이/삼...)
    수사 체계를 쓴다는 규칙 자체를 명시적으로 검증한다."""

    def test_native_units_use_native_numerals(self):
        self.assertEqual(normalize_for_speech("1개"), "한 개")
        self.assertEqual(normalize_for_speech("1명"), "한 명")
        self.assertEqual(normalize_for_speech("1시간"), "한 시간")

    def test_sino_units_use_sino_numerals_not_native(self):
        self.assertEqual(normalize_for_speech("1%"), "일 퍼센트")
        self.assertEqual(normalize_for_speech("1km"), "일 킬로미터")
        self.assertEqual(normalize_for_speech("1kg"), "일 킬로그램")

    def test_twenty_native_is_irregular_seumu(self):
        self.assertEqual(normalize_for_speech("20번"), "스무 번")

    def test_twenty_one_native_combines_tens_and_ones(self):
        self.assertEqual(normalize_for_speech("21번"), "스물한 번")

    def test_ten_sino_omits_leading_il(self):
        self.assertEqual(normalize_for_speech("10%"), "십 퍼센트")

    def test_eleven_sino_keeps_place_and_digit(self):
        self.assertEqual(normalize_for_speech("11kg"), "십일 킬로그램")


if __name__ == "__main__":
    unittest.main()
