import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.subtitle_service import (
    MAX_CHARS,
    MIN_CHARS,
    _split_sentence_by_words,
    split_subtitle,
)


class TestSplitSentenceByWords(unittest.TestCase):

    def test_short_text_returned_as_is(self):
        self.assertEqual(_split_sentence_by_words("짧은 문장", 18), ["짧은 문장"])

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(_split_sentence_by_words("", 18), [])

    def test_never_splits_within_a_word(self):
        text = "일어나자마자 마시는 미지근한 물 한 잔"
        pieces = _split_sentence_by_words(text, 10)
        original_words = text.split()
        reconstructed_words = " ".join(pieces).split()
        self.assertEqual(reconstructed_words, original_words)

    def test_no_tiny_orphan_fragment(self):
        text = "일어나자마자 마시는 미지근한 물 한 잔"
        pieces = _split_sentence_by_words(text, 18)
        self.assertNotIn("한 잔", pieces)
        for piece in pieces:
            self.assertGreaterEqual(len(piece), 4)

    def test_pieces_fit_within_max_when_splittable(self):
        text = "밤새 쌓인 노폐물을 씻어내고 신진대사를 깨워주는 가장 간단한 방법이죠"
        pieces = _split_sentence_by_words(text, 18)
        for piece in pieces:
            self.assertLessEqual(len(piece), 18)

    def test_single_word_longer_than_max_is_not_broken(self):
        # 공백이 전혀 없는 단일 "단어"는 글자 단위로 쪼개지 않고
        # 그대로 하나의 조각으로 남는다.
        text = "가" * 30
        self.assertEqual(_split_sentence_by_words(text, 18), [text])

    def test_comma_before_word_never_produces_standalone_fragment(self):
        # "대신,"처럼 쉼표가 붙은 짧은 절이 더 이상 단독 자막 조각으로
        # 남지 않고 다음 단어들과 함께 묶여야 한다.
        text = "대신, 일어나자마자 커튼을 활짝 열어 햇빛을 쬐세요"
        pieces = _split_sentence_by_words(text, 18)
        self.assertNotIn("대신,", pieces)
        for piece in pieces:
            self.assertGreaterEqual(len(piece), MIN_CHARS)


class TestSplitSubtitle(unittest.TestCase):

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(split_subtitle(""), [])

    def test_short_sentence_kept_whole(self):
        self.assertEqual(split_subtitle("오늘은 좋은 날."), ["오늘은 좋은 날."])

    def test_splits_on_period_boundaries_first(self):
        result = split_subtitle("짧다. 이것도 짧다.")
        self.assertEqual(result, ["짧다.", "이것도 짧다."])

    def test_splits_on_question_and_exclamation(self):
        result = split_subtitle("정말요? 대박!")
        self.assertEqual(result, ["정말요?", "대박!"])

    def test_no_word_ever_split_mid_word(self):
        text = (
            "일어나자마자 마시는 미지근한 물 한 잔, 밤새 쌓인 노폐물을 "
            "씻어내고 신진대사를 깨워주는 가장 간단한 방법이죠."
        )
        result = split_subtitle(text)

        def normalize(s):
            return s.replace(",", " ").replace(".", " ").split()

        self.assertEqual(normalize(" ".join(result)), normalize(text))

    def test_no_tiny_orphan_fragment_in_real_example(self):
        text = (
            "일어나자마자 마시는 미지근한 물 한 잔, 밤새 쌓인 노폐물을 "
            "씻어내고 신진대사를 깨워주는 가장 간단한 방법이죠."
        )
        result = split_subtitle(text)

        for piece in result:
            self.assertGreater(len(piece.strip()), 2)

    def test_pieces_generally_fit_within_max_chars(self):
        text = (
            "억지로 울리는 알람 대신, 커튼을 열고 햇살로 잠을 깨보세요. "
            "우리 몸의 생체 시계가 정상으로 돌아오기 시작하거든요."
        )
        result = split_subtitle(text)
        for piece in result:
            self.assertLessEqual(len(piece), MAX_CHARS)

    def test_no_isolated_comma_clause_regression(self):
        # 실제 e2e 테스트 영상(20260706_003417)에서 관찰된 문제:
        # "대신,"이 문장 맨 앞 쉼표절이라 단독 자막으로 남았었다.
        text = "당신의 하루를 망치는 지름길입니다. 대신, 일어나자마자 커튼을 활짝 열어 햇빛을 쬐세요."
        result = split_subtitle(text)

        self.assertNotIn("대신,", result)
        for piece in result:
            self.assertGreaterEqual(len(piece.strip()), 4)

    def test_never_produces_a_fragment_shorter_than_min_chars_when_avoidable(self):
        text = "그리고 공복에 미지근한 물 한 잔!"
        result = split_subtitle(text)

        for piece in result:
            self.assertGreaterEqual(len(piece.strip()), 4)


if __name__ == "__main__":
    unittest.main()
