"""
Sprint94 - Metadata Quality, 한국어 명사 추출.

여기 있는 실패 사례는 전부 실제 대본에서 나온 것이다. Sprint93이
만든 해시태그를 눈으로 보고 하나씩 잡았고, 잡을 때마다 원인이
달랐다 - 그 원인들을 그대로 테스트로 옮겼다.

  #손에 #컵을      조사 부착형
  #들다가 #넘기면   동사 활용형
  #그냥 #방금       부사
  #마시 #쌓이 #깨우 "는"을 조사로 오인(관형사형 어미다)
  #제대            "제대로"에서 "로"를 조사로 오인
  #피곤해서         강한 조사를 뗀 뒤 활용형 검사를 안 함
  #간단 #미지근     "한"을 서술성 명사 꼬리로 오인(형용사다)

AI를 부르지 않는다. 형태소 분석기도 쓰지 않는다.
"""

import ast
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import korean_noun_filter as nf


class TestTheActualFailuresFromSprint93(unittest.TestCase):
    """실제로 채널 설명란에 나갔던 것들이다."""

    def test_a_particle_attached_form_is_reduced_not_kept(self):
        nouns = nf.extract_nouns("아침에 컵을 들다가 손에 힘이 빠졌습니다")

        self.assertNotIn("손에", nouns)
        self.assertNotIn("컵을", nouns)

    def test_verb_conjugations_are_rejected(self):
        nouns = nf.extract_nouns("컵을 들다가 그냥 넘기면 평생 후회합니다")

        for bad in ("들다가", "넘기면", "후회합니다"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, nouns)

    def test_adverbs_are_rejected(self):
        nouns = nf.extract_nouns(
            "그냥 방금 혹시 정말 특히 절대 제대로 평생 아침에 혈압이 올랐습니다",
        )

        for bad in ("그냥", "방금", "혹시", "정말", "특히", "절대",
                    "제대로", "제대", "평생"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, nouns)

    def test_an_adnominal_ending_is_not_mistaken_for_a_particle(self):
        """"마시는/쌓이는"의 "는"은 조사가 아니라 관형사형 어미다.
        조사로 읽으면 동사 어간이 명사 행세를 한다."""

        nouns = nf.extract_nouns(
            "커피를 마시는 습관이 위벽에 쌓이는 자극을 깨우는 원인입니다",
        )

        for bad in ("마시", "쌓이", "깨우"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, nouns)

    def test_a_predicate_survives_even_after_a_strong_particle(self):
        """"피곤해서가"의 "가"를 떼면 "피곤해서"가 남는다."""

        self.assertNotIn("피곤해서", nf.extract_nouns("이건 그냥 피곤해서가 아닙니다"))

    def test_adjective_stems_are_not_treated_as_nouns(self):
        """"간단한/미지근한"의 앞부분은 형용사 어간이다."""

        nouns = nf.extract_nouns("간단한 방법이고 미지근한 물이 좋습니다")

        self.assertNotIn("간단", nouns)
        self.assertNotIn("미지근", nouns)


class TestPastTenseIsNotANoun(unittest.TestCase):
    """"켜졌을"의 "을"은 목적격 조사가 아니라 관형사형 어미다("켜졌을
    때"). 조사로 떼면 "켜졌"이 남아 명사 행세를 한다 - 실제 영상
    3편 검증에서 나왔다."""

    def test_a_past_tense_stem_left_by_a_particle_strip_is_rejected(self):
        nouns = nf.extract_nouns("혈관에 적신호가 켜졌을 때를 조심하세요")

        self.assertNotIn("켜졌", nouns)
        self.assertIn("적신호", nouns)

    def test_other_past_tense_forms_are_rejected_too(self):
        nouns = nf.extract_nouns(
            "수치가 올랐을 때, 물을 마셨을 무렵, 결과가 나왔을 즈음",
        )

        for bad in ("올랐", "마셨", "나왔"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, nouns)


class TestTheTopicIsRead(unittest.TestCase):
    """"치매를 늦추는 생활 습관"으로 만든 영상에서 해시태그에 "치매"가
    빠졌다(실측). 대본에는 "치매"가 조사 없이만 나와 증거가 없었고,
    정작 주제어에는 "치매를"이 있었다."""

    def test_a_subject_noun_only_present_in_the_topic_is_recovered(self):
        script = {"title": "절대 치매 안 걸리는 사람들의 '이것' 하나",
                  "script": "치매? 아직 포기하긴 이릅니다. 뇌세포가 자극을 받습니다."}

        without = nf.extract_nouns_from_script(script)
        with_topic = nf.extract_nouns_from_script(script, "치매를 늦추는 생활 습관")

        self.assertNotIn("치매", without)
        self.assertIn("치매", with_topic)

    def test_the_topic_is_optional(self):
        script = {"title": "혈압 관리", "script": "혈압이 중요합니다."}

        self.assertIn("혈압", nf.extract_nouns_from_script(script))


class TestRealNounsSurvive(unittest.TestCase):
    """거르기만 하면 고친 것이 아니다."""

    def test_the_subject_nouns_are_found(self):
        nouns = nf.extract_nouns(
            "혈압이 높으면 혈관에 염증이 생기고 콜레스테롤이 쌓입니다",
        )

        for good in ("혈압", "혈관", "염증", "콜레스테롤"):
            with self.subTest(good=good):
                self.assertIn(good, nouns)

    def test_a_predicate_noun_is_recovered(self):
        """"관리합니다"의 "관리"는 명사다(서술성 명사)."""

        self.assertIn("관리", nf.extract_nouns("혈압을 꾸준히 관리합니다"))

    def test_repeated_particle_forms_collapse_to_one_noun(self):
        nouns = nf.extract_nouns("혈압이 오르고 혈압을 낮추고 혈압은 중요합니다")

        self.assertEqual(nouns.count("혈압"), 1)

    def test_the_most_frequent_noun_comes_first(self):
        nouns = nf.extract_nouns(
            "혈관이 혈관을 혈관의 상태입니다. 커피가 나옵니다.",
        )

        self.assertEqual(nouns[0], "혈관")


class TestSingleCharacterAndEmptyInput(unittest.TestCase):

    def test_a_one_character_stem_is_dropped(self):
        """"손에"->"손"은 실제 명사지만 한 글자 해시태그는 쓸모가 없다."""

        self.assertNotIn("손", nf.extract_nouns("손에 힘이 빠집니다"))

    def test_empty_text_gives_an_empty_list(self):
        self.assertEqual(nf.extract_nouns(""), [])
        self.assertEqual(nf.extract_nouns(None), [])

    def test_a_script_without_a_body_still_works(self):
        self.assertIsInstance(
            nf.extract_nouns_from_script({"title": "혈압 관리법"}), list,
        )


class TestNoAnalyzerAndNoAI(unittest.TestCase):

    def test_it_imports_nothing_but_the_standard_library(self):
        tree = ast.parse(open(nf.__file__, encoding="utf-8").read())

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")

        self.assertEqual(imported, {"re", "typing"})

    def test_no_korean_analyzer_dependency_was_added(self):
        for banned in ("konlpy", "kiwipiepy", "mecab", "soynlp"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, sys.modules)


if __name__ == "__main__":
    unittest.main()
