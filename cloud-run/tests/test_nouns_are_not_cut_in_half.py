"""
Sprint240 - 낱말을 반으로 자르지 않는다 (Metadata Quality).

무엇이 실제로 나갔나
--------------------
2026-08-19, 실제 YouTube 에 이 태그가 붙어 올라갔다.

    ["해결", "앞쪽", "충분", "발목", "손으", "뒤꿈치", "엉덩", "쪽으",
     "허리", "똑같"]

"손으" · "쪽으" · "엉덩" 은 한국어 낱말이 아니다. 대본의 이 문장에서
나왔다.

    "한쪽 발목을 손으로 잡고 뒤꿈치를 엉덩이 쪽으로..."

원인은 조사를 떼는 자리에 있다
------------------------------
_strip_suffix 는 긴 꼬리부터 보되, **떼고 남는 것이 두 글자 미만이면
건너뛰고 다음 꼬리를 본다.**

    손으로
      꼬리 '으로'  남는 것 '손'   길이 1  -> 길이 미달로 건너뜀
      꼬리 '로'    남는 것 '손으'  길이 2  -> 채택          <- 여기다

옳은 답은 "덜 뗀다" 가 아니라 "떼지 않는다(그 낱말은 버린다)" 이다.
'으로' 가 조사인 것은 맞고, 떼면 '손' 이 남는데 그것이 짧아서 못 쓸
뿐이다. 짧아서 못 쓰는 것을 짧지 않게 만들려고 조사 한 글자를 낱말에
남기면, 사람이 읽을 수 없는 것이 채널에 나간다.

이 시험이 지키는 것
-------------------
꼬리 하나를 떼기로 정했으면 **가장 긴 것 하나**만 본다. 그것이 길이
때문에 안 되면 그 낱말은 후보에서 빠진다 - 다른 꼬리로 갈아타지
않는다.

무엇을 고치지 않는가
--------------------
"엉덩이" -> "엉덩" 은 다른 병이다. '이' 는 진짜 조사이고 '엉덩이' 는
진짜 낱말이라, 사전 없이 규칙만으로는 가를 수 없다. 이 파일은 그것을
고치지 않고 **사실로 적어 둔다** - 고친 척하지 않기 위해서다.
"""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import korean_noun_filter as filter

REAL_PROJECT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output", "20260819_221236",
)


class TheParticleIsStrippedWholeOrNotAtAllTest(unittest.TestCase):
    """
    이 파일의 중심이다. 긴 꼬리가 길이 때문에 막히면 짧은 꼬리로
    갈아타지 않는다.
    """

    def test_으로_가_막히면_로_로_갈아타지_않는다(self):
        for word in ("손으로", "쪽으로", "앞으로", "위로"):
            with self.subTest(word=word):
                found = filter._strip_particles(word)

                self.assertNotIn(found, ("손으", "쪽으", "앞으", "위"),
                                 f"{word} -> {found}")

    def test_남는_말이_온전하다(self):
        """
        떼고 남은 것이 조사 조각을 물고 있으면 안 된다. '으' 하나로
        끝나는 한국어 명사는 사실상 없다.
        """

        for word in ("손으로", "쪽으로", "앞으로", "밖으로", "안으로"):
            with self.subTest(word=word):
                self.assertFalse(
                    filter._strip_particles(word).endswith("으"),
                    f"{word} -> {filter._strip_particles(word)}")

    def test_원래_잘_되던_것은_그대로다(self):
        """고치면서 되던 것을 깨지 않는다."""

        for word, want in (
            ("발목을", "발목"), ("뒤꿈치를", "뒤꿈치"), ("허리를", "허리"),
            ("무릎이", "무릎"), ("스트레칭을", "스트레칭"),
            ("근육이", "근육"), ("혈압으로는", "혈압"),
            ("대퇴사두근", "대퇴사두근"),
        ):
            with self.subTest(word=word):
                self.assertEqual(filter._strip_particles(word), want)

    def test_영문과_숫자는_건드리지_않는다(self):
        for word in ("Pexels", "AI", "3D", "MRI", "COVID19"):
            with self.subTest(word=word):
                self.assertEqual(filter._strip_particles(word), word)


class TheTagsAreRealWordsTest(unittest.TestCase):
    """
    실제로 올라간 그 대본으로 잰다. 지어낸 문장이 아니다.
    """

    def _script(self):
        where = os.path.join(REAL_PROJECT, "script.json")

        if not os.path.isfile(where):
            self.skipTest("실제 프로젝트가 없다")

        with open(where, encoding="utf-8") as f:
            return json.load(f)

    def test_잘린_조각이_태그가_되지_않는다(self):
        """
        실측에서 나온 그 셋. 이것이 다시 나오면 같은 것이 또 채널에
        나간다.
        """

        found = filter.extract_nouns_from_script(self._script())

        for cut in ("손으", "쪽으", "앞으"):
            with self.subTest(cut=cut):
                self.assertNotIn(cut, found)

    def test_쓸_만한_명사는_여전히_나온다(self):
        """
        잘린 것을 없애느라 멀쩡한 것까지 사라지면 태그가 빈다.
        """

        found = filter.extract_nouns_from_script(self._script())

        self.assertGreaterEqual(len(found), 5, found)

        for want in ("발목", "뒤꿈치", "허리"):
            with self.subTest(want=want):
                self.assertIn(want, found)

    def test_어느_태그도_조사_조각으로_끝나지_않는다(self):
        found = filter.extract_nouns_from_script(self._script())

        for noun in found:
            with self.subTest(noun=noun):
                self.assertFalse(noun.endswith("으"), noun)

    def test_같은_대본이면_같은_태그가_나온다(self):
        """
        deterministic 해야 fixture 로 쓸 수 있고, 사람이 어제와 오늘을
        견줄 수 있다.
        """

        script = self._script()

        first = filter.extract_nouns_from_script(script)
        second = filter.extract_nouns_from_script(script)

        self.assertEqual(first, second)


class TheYouTubeLimitsAreRespectedTest(unittest.TestCase):
    """
    YouTube 는 태그 하나에 500자, 전체 500자를 넘기지 않기를 요구한다.
    낱말을 온전히 두면서 그 안에 들어와야 한다.
    """

    def _tags(self):
        from app.services import hashtag_generator

        where = os.path.join(REAL_PROJECT, "script.json")

        if not os.path.isfile(where):
            self.skipTest("실제 프로젝트가 없다")

        with open(where, encoding="utf-8") as f:
            return hashtag_generator.generate_seo_keywords(json.load(f))

    def test_태그_하나가_지나치게_길지_않다(self):
        for tag in self._tags():
            with self.subTest(tag=tag):
                self.assertLessEqual(len(tag), 100, tag)

    def test_모두_더해도_한도_안이다(self):
        tags = self._tags()

        # 쉼표로 이어 보내므로 그것까지 센다.
        total = sum(len(tag) for tag in tags) + max(0, len(tags) - 1)

        self.assertLessEqual(total, 500, f"{total}자")

    def test_빈_것이_섞이지_않는다(self):
        for tag in self._tags():
            with self.subTest(tag=tag):
                self.assertTrue(tag.strip(), repr(tag))


class WhatIsStillWrongTest(unittest.TestCase):
    """
    고치지 않은 것을 적어 둔다. 고친 척하는 것이 가장 나쁘다.

    "엉덩이" 의 '이' 는 진짜 조사이고 "엉덩이" 는 진짜 낱말이다.
    사전 없이 규칙만으로는 가를 수 없다 - 이 저장소는 형태소 분석기를
    들이지 않기로 했고(korean_noun_filter 머리말), 그 결정은 그대로다.

    이 시험은 그 한계를 **지금 사실 그대로** 붙잡아 둔다. 언젠가
    사전이 들어와 고쳐지면 이 시험이 먼저 깨지고, 그때 지우면 된다.
    """

    def test_한_글자_조사로_끝나는_명사는_아직_잘린다(self):
        self.assertEqual(filter._strip_particles("엉덩이"), "엉덩")

        # 같은 부류. 사전이 없으면 가릴 수 없다.
        self.assertEqual(filter._strip_particles("목이"), "목이")


if __name__ == "__main__":
    unittest.main()
