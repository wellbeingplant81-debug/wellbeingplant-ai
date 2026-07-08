import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.subtitle_service import (
    CUE_GROUPING_MAX_CHARS,
    MAX_CHARS,
    MIN_CHARS,
    SAFE_AREA_MAX_LINE_WIDTH,
    _display_width,
    _split_sentence_by_words,
    create_subtitle,
    split_subtitle,
    wrap_to_safe_lines,
)
from app.services.subtitle_placement_service import POSITION_BOTTOM, POSITION_TOP


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
        # Sprint39: 조각 하나가 최대 2줄(CUE_GROUPING_MAX_CHARS)까지
        # 늘어날 수 있다 - 실제 화면 줄바꿈은 wrap_to_safe_lines()가
        # 별도로 처리하므로 조각 자체는 예전 MAX_CHARS(1줄)보다 커도 된다.
        text = (
            "억지로 울리는 알람 대신, 커튼을 열고 햇살로 잠을 깨보세요. "
            "우리 몸의 생체 시계가 정상으로 돌아오기 시작하거든요."
        )
        result = split_subtitle(text)
        for piece in result:
            self.assertLessEqual(len(piece), CUE_GROUPING_MAX_CHARS)

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


class TestDisplayWidth(unittest.TestCase):

    def test_empty_string_is_zero(self):
        self.assertEqual(_display_width(""), 0)

    def test_korean_characters_count_as_two(self):
        self.assertEqual(_display_width("가나다"), 6)

    def test_ascii_characters_count_as_one(self):
        self.assertEqual(_display_width("abc"), 3)

    def test_mixed_text_sums_both(self):
        self.assertEqual(_display_width("가a"), 3)


class TestWrapToSafeLines(unittest.TestCase):

    def test_short_text_is_not_wrapped(self):
        self.assertEqual(wrap_to_safe_lines("짧은 자막", 34), "짧은 자막")

    def test_never_splits_within_a_word(self):
        text = "일어나자마자 마시는 미지근한 물 한 잔"
        wrapped = wrap_to_safe_lines(text, 10)
        rejoined_words = wrapped.replace("\n", " ").split()
        self.assertEqual(rejoined_words, text.split())

    def test_default_safe_area_width_is_calibrated_against_real_rendering(self):
        # 2026-07-06 실측(final_video_service.py와 동일한 force_style로
        # 1080x1920에 실제 렌더링해 픽셀 단위로 측정) 결과, 이전 값(34)은
        # 실제보다 훨씬 관대해서 화면 잘림이 발생했다. 재보정된 기본값은
        # 훨씬 작아야 한다 - 이 상수가 실수로 다시 커지는 회귀를 막는다.
        self.assertLess(SAFE_AREA_MAX_LINE_WIDTH, 25)

    def test_real_overflowing_example_now_wraps_with_default_width(self):
        # E2E 실측에서 실제로 화면 밖으로 잘려나갔던 문구
        # ("아침에 마시는 물 한 잔이", display_width=24). 재보정된
        # 기본 SAFE_AREA_MAX_LINE_WIDTH를 쓰면 이제 반드시 줄바꿈되어야
        # 한다(이전엔 34 이하라 한 줄로 그대로 나가 화면 밖으로 잘렸다).
        text = "아침에 마시는 물 한 잔이"

        wrapped = wrap_to_safe_lines(text)

        self.assertIn("\n", wrapped)

        for line in wrapped.split("\n"):
            self.assertLessEqual(_display_width(line), SAFE_AREA_MAX_LINE_WIDTH)

    def test_real_example_prefers_balanced_semantic_split_over_greedy_fill(self):
        # 사용자가 제시한 실제 사례: 그리디하게 앞줄을 꽉 채우면
        # "...한 잔"까지 몰아넣고 둘째 줄에 "이"류의 짧은 조각만 남아
        # 어색해진다. 균형/의미 우선 분할은 훨씬 자연스러운 지점에서
        # 끊어야 한다.
        text = "아침 공복에 마시는 '이 물' 한 잔이"

        wrapped = wrap_to_safe_lines(text, 20)

        self.assertEqual(wrapped, "아침 공복에 마시는\n'이 물' 한 잔이")

    def test_prefers_comma_boundary_over_pure_balance(self):
        # 쉼표 뒤에서 끊는 지점이 있으면, 폭이 더 균형 잡힌 다른
        # 지점보다 쉼표 지점을 우선해야 한다.
        text = "대신, 일어나자마자 커튼을 활짝 열어 햇빛을 쬐세요"

        wrapped = wrap_to_safe_lines(text, 45)

        first_line = wrapped.split("\n")[0]
        self.assertTrue(first_line.rstrip().endswith(","))

    def test_never_breaks_inside_a_quoted_phrase(self):
        text = "이것은 정말 '아주 중요한 습관' 입니다"

        wrapped = wrap_to_safe_lines(text, 14)

        lines = wrapped.split("\n")
        # 따옴표로 감싼 구가 한쪽 줄에 온전히 있어야 한다(양쪽에 걸쳐
        # 쪼개지면 안 됨).
        self.assertTrue(
            any("'아주 중요한 습관'" in line for line in lines)
        )

    def test_prefers_conjunction_start_of_next_line(self):
        text = "물을 챙겨 드세요 그리고 항상 건강하시길 바랍니다"

        wrapped = wrap_to_safe_lines(text, 20)

        lines = wrapped.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("그리고"))

    def test_avoids_leaving_a_lone_particle_line(self):
        # 마지막 줄이 조사 붙은 단어 하나만 남는 분할은 피해야 한다.
        text = "아침 공복에 마시는 물 한 잔이"

        wrapped = wrap_to_safe_lines(text, 20)

        lines = wrapped.split("\n")
        last_line_words = lines[-1].split()
        self.assertFalse(
            len(last_line_words) == 1 and _display_width(lines[-1]) <= 6
        )

    def test_falls_back_gracefully_when_no_split_fits_both_lines(self):
        text = "가나다라마바사 아자차카타파하 거너더러머버서"

        wrapped = wrap_to_safe_lines(text, 8)

        rejoined_words = wrapped.replace("\n", " ").split()
        self.assertEqual(rejoined_words, text.split())


class TestCreateSubtitlePositionTags(unittest.TestCase):
    """Sprint57 - Smart Subtitle Placement v1. create_subtitle()가
    scene별로 choose_subtitle_position() 결과를 SRT 텍스트 맨 앞에
    ASS override tag({\\an8}=상단, {\\an2}=하단)로 심는지 검증한다.
    실제 이미지 복잡도 분석(subtitle_placement_service 자체)은 이미
    별도 테스트로 커버되므로, 여기서는 choose_subtitle_position을
    mock으로 고정해 배선만 확인한다."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_path = os.path.join(self.tmp_dir, "project")
        os.makedirs(os.path.join(self.project_path, "audio", "scenes"))
        os.makedirs(os.path.join(self.project_path, "images"))

        scenes = [
            {"scene": 1, "narration": "안녕하세요.", "image_prompt": "p1"},
            {"scene": 2, "narration": "반갑습니다.", "image_prompt": "p2"},
        ]

        with open(os.path.join(self.project_path, "script.json"), "w", encoding="utf-8") as f:
            json.dump({"scenes": scenes}, f, ensure_ascii=False)

        for i in (1, 2):
            audio_path = os.path.join(self.project_path, "audio", "scenes", f"scene{i}.mp3")
            result = subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-t", "2.0",
                 "-i", "anullsrc=r=44100:cl=mono", "-c:a", "libmp3lame", audio_path],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _read_srt(self):
        with open(
            os.path.join(self.project_path, "subtitle", "subtitle.srt"),
            "r", encoding="utf-8",
        ) as f:
            return f.read()

    @patch(
        "app.services.subtitle_service.choose_subtitle_position",
        side_effect=[POSITION_TOP, POSITION_BOTTOM],
    )
    def test_scene_positions_are_embedded_as_ass_override_tags(self, mock_choose):
        create_subtitle(self.project_path)

        srt_text = self._read_srt()

        self.assertIn(r"{\an8}안녕하세요.", srt_text)
        self.assertIn(r"{\an2}반갑습니다.", srt_text)

    @patch(
        "app.services.subtitle_service.choose_subtitle_position",
        return_value=POSITION_BOTTOM,
    )
    def test_position_is_resolved_once_per_scene_not_per_cue(self, mock_choose):
        create_subtitle(self.project_path)

        self.assertEqual(mock_choose.call_count, 2)

    @patch(
        "app.services.subtitle_service.choose_subtitle_position",
        return_value=POSITION_TOP,
    )
    def test_existing_srt_structure_is_unchanged_besides_tag(self, mock_choose):
        create_subtitle(self.project_path)

        srt_text = self._read_srt()

        self.assertIn("-->", srt_text)
        self.assertTrue(srt_text.strip().startswith("1"))


if __name__ == "__main__":
    unittest.main()
