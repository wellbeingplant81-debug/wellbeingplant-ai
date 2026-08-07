"""
Sprint137 - 재 본 것만 잰 값으로 말한다 (Epic 56, Phase 14).

Sprint136에서 비교 표를 만들며 드러난 모순을 닫는다. 표는 "미측정"이라
적는데 바로 위 카드는 같은 Provider에 ★★★★를 그리고 있었다. 한
화면이 두 말을 하고 있었던 것이다.

별은 등급이고 등급은 의견이다
-----------------------------
quality_tier는 Provider가 스스로 신고한 값이지 측정이 아니다. 게다가
지금 전부 같은 값(standard)이라, 화면에 옮기면 아무 사실도 전하지
못한 채 등급처럼 읽힌다.

속도와 비용의 별도 같은 문제였다. 초와 단계 수는 사실이지만, 그것을
1~5로 환산하는 순간 "빠르다 느리다"와 "싸다 비싸다"라는 판정이 된다.
숫자는 사실이고 별은 의견이다.

무엇을 실제로 쟀는가
--------------------
    잰 것    제작 시간 - stageSpec.sample_size편의 중앙값
    안 잰 것 품질 · 금액

그래서 시간은 숫자로 적고 "측정 완료"라 말하고, 나머지는 "미측정"이라
적는다.

세 곳이 같은 말을 한다
----------------------
    Provider Card   미측정
    Summary         품질 미측정 · 제작시간 측정 완료 · 비용 미측정
    비교 표         Current만 측정 완료, 나머지 미측정
"""

import os
import re
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)

# 재 본 적이 없는 것에 매기는 말들.
BANNED = ("★", "☆", "높음", "낮음", "최고", "가성비", "저렴", "비쌈",
          "빠름", "느림")


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script():
    page = _page()
    return page[page.index("<script>"):]


def _without_comments(block):
    """
    설명을 걷어낸 코드.

    왜 어떤 말을 쓰지 않는지 적으려면 그 말을 적어야 한다. 원문을
    훑으면 그 설명 자체가 걸린다 - 이 저장소가 여러 번 겪은 결함이다.
    """

    return re.sub(r"//.*", "", block)


def _function(name):
    script = _script()
    block = script[script.index(f"function {name}("):]
    end = block.find("\nfunction ", 1)

    return block if end < 0 else block[:end]


class TestTheStarsAreGone(unittest.TestCase):

    def test_no_star_is_drawn_anywhere(self):
        page = _without_comments(_page())

        for mark in ("★", "☆"):
            with self.subTest(mark=mark):
                self.assertNotIn(mark, page)

    def test_the_star_helpers_are_gone_too(self):
        """부르는 자리가 없는데 남겨 두면 다음 사람이 다시 쓴다."""

        script = _script()

        for name in ("function starText", "const STARS",
                     "function speedStars", "function costStars",
                     "function planQuality"):
            with self.subTest(name=name):
                self.assertNotIn(name, script)

    def test_the_reported_tier_no_longer_reaches_the_screen(self):
        """전부 같은 값이라 옮겨 적어도 사실을 전하지 못한다."""

        self.assertNotIn("provider_quality", _without_comments(_script()))

    def test_no_grading_word_is_left(self):
        script = _without_comments(_script())

        for word in BANNED:
            with self.subTest(word=word):
                self.assertNotIn(word, script)


class TestTheTwoWordsAreDeclaredOnce(unittest.TestCase):

    def test_both_words_exist(self):
        script = _script()

        self.assertIn('const MEASURED = "측정 완료"', script)
        self.assertIn('const UNMEASURED = "미측정"', script)

    def test_nobody_writes_them_by_hand(self):
        """두 벌이 되면 한쪽만 바뀌는 날이 온다."""

        script = _without_comments(_script())

        self.assertEqual(script.count('"측정 완료"'), 1)
        self.assertEqual(script.count('"미측정"'), 1)


class TestTheThreePlacesAgree(unittest.TestCase):

    def test_the_card_says_unmeasured(self):
        block = _function("providerCard")

        self.assertIn("UNMEASURED", block)

    def test_the_compare_table_says_the_same(self):
        block = _function("providerMeasured")

        self.assertIn("UNMEASURED", block)
        self.assertIn("MEASURED", block)

    def test_the_summary_says_the_same(self):
        block = _function("expectedResult")

        self.assertIn("UNMEASURED", block)
        self.assertIn("MEASURED", block)


class TestOnlyTheMeasuredThingIsCalledMeasured(unittest.TestCase):

    def test_quality_is_unmeasured_in_the_summary(self):
        block = _function("expectedResult")
        quality = block[block.index("품질"):block.index("제작시간")]

        self.assertIn("UNMEASURED", quality)
        self.assertNotIn("MEASURED }", quality)

    def test_time_keeps_its_measured_number_and_basis(self):
        """숫자는 사실이다. 지우지 않는다."""

        block = _function("expectedResult")
        time = block[block.index("제작시간"):block.index("비용")]

        self.assertIn("estimated_seconds", time)
        self.assertIn("sample_size", time)
        self.assertIn("MEASURED", time)

    def test_cost_is_unmeasured_and_says_why(self):
        block = _function("expectedResult")
        cost = block[block.index("비용"):]

        self.assertIn("UNMEASURED", cost)
        self.assertIn("단가", cost)

    def test_the_compare_table_only_measures_current(self):
        block = _function("providerMeasured")

        self.assertIn('providerKind(p) === "Current"', block)
        self.assertIn("seconds_if_generated", block)


class TestNothingBelowTheScreenMoved(unittest.TestCase):
    """Pipeline · Resolver · Bridge · Provider · Review · Router 0줄."""

    def test_the_router_still_reports_the_tier_it_always_did(self):
        """화면이 그리지 않기로 한 것뿐이다 - 서버는 그대로다."""

        from fastapi.testclient import TestClient

        from app.main import app

        payload = TestClient(app).get(
            "/studio/api/production/stages").json()
        row = next(s for s in payload["stages"] if s["stage"] == "script")

        self.assertIn("provider_quality", row)
        self.assertEqual(row["provider_list"][0]["quality_tier"], "standard")

    def test_the_registry_still_declares_a_tier(self):
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        for provider in registry.for_stage("script"):
            with self.subTest(provider=provider.name):
                self.assertTrue(provider.capabilities.quality_tier)

    def test_only_the_page_changed(self):
        from app.routers import studio

        with open(studio.__file__, encoding="utf-8") as f:
            source = f.read()

        # 라우터가 쓰는 이름들. 여기에 화면의 두 낱말이 섞여
        # 들어갔는지 본다 - 원문을 훑으면 MEASURED_AT처럼 이 글자를
        # 품은 기존 이름에 걸린다. 그것은 이번에 만든 것이 아니다.
        names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", source))

        for name in ("MEASURED", "UNMEASURED"):
            with self.subTest(name=name):
                self.assertNotIn(name, names)

        self.assertNotIn("미측정", source)


class TestTheHandlersStillLineUp(unittest.TestCase):
    """지운 이름을 부르는 자리가 남으면 화면이 죽는다."""

    def test_every_handler_the_markup_calls_is_declared(self):
        page = _page()
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])

    def test_no_call_points_at_a_deleted_helper(self):
        script = _without_comments(_script())

        for gone in ("starText(", "planQuality(", "speedStars(",
                     "costStars(", "STARS["):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, script)


if __name__ == "__main__":
    unittest.main()
