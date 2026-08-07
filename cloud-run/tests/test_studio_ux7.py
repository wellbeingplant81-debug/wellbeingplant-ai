"""
Sprint120 - Studio UX 6.0 (Epic 54, Phase 20).

사용자가 단계마다 고르는 대신, 가진 것을 체크하면 AI가 먼저 추천하고
사용자는 고치기만 한다.

지난 화면은 라디오 하나로 다섯 상황 중 하나를 고르게 했다. 그것은
"대본은 있는데 음성만 없다" 같은 조합을 표현할 수 없었다. 체크박스는
그 조합을 그대로 받는다 - 가진 것은 서로 독립이기 때문이다.

추천 규칙은 하나뿐이다.

    체크했다   그 단계는 직접 준다
    안 했다    그 단계는 AI가 만든다

제작 준비도도 새로 계산하지 않는다.

    직접 제공 / AI 생성   준비됨
    사용 안 함 / Provider 없음   아님

준비도가 100이 아니어도 막지 않는다. 짧은 영상이 필요한 날도 있고,
그 판단을 우리가 대신할 근거가 없다(Sprint108이 대본 길이에서 내린
것과 같은 결론이다).
"""

import ast
import os
import re
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _page():
    return client.get("/studio").text


def _block(page, start, end="\nfunction "):
    cut = page[page.index(start):]
    return cut[:cut.index(end)]


class TestTheQuestionIsCheckboxes(unittest.TestCase):

    def test_the_title_asks_what_is_ready(self):
        self.assertIn("이미 준비된 자료가 있나요?", _page())

    def test_the_four_items_are_offered(self):
        page = _page()
        block = _block(page, "const HAVE_ITEMS", "\n];")

        for label in ("대본", "이미지", "내 목소리", "메타데이터"):
            with self.subTest(label=label):
                self.assertIn(label, block)

    def test_they_are_checkboxes_not_radios(self):
        page = _page()
        block = _block(page, "function haveCard")

        self.assertIn('type="checkbox"', block)
        self.assertNotIn('type="radio"', block)

    def test_more_than_one_can_be_ticked(self):
        """가진 것은 서로 독립이다 - 대본만 있고 음성은 없을 수 있다."""

        page = _page()
        block = _block(page, "function toggleHave")

        self.assertIn("have[", block)
        self.assertNotIn("HAVE_ITEMS.forEach", block)

    def test_every_item_maps_to_a_real_stage(self):
        page = _page()
        block = _block(page, "const HAVE_ITEMS", "\n];")
        stages = set(re.findall(r'stage:"(\w+)"', block))

        served = {r["stage"] for r
                  in client.get("/studio/api/production/stages").json()["stages"]}

        self.assertTrue(stages)
        self.assertTrue(stages <= served)


class TestTheRecommendButton(unittest.TestCase):

    def test_it_exists(self):
        page = _page()

        self.assertIn('id="recommend"', page)
        self.assertIn("AI 추천", page)

    def test_the_rule_is_the_only_one(self):
        """체크했으면 직접, 아니면 AI. 그 이상은 없다.

        어느 선택지를 쓸지는 HAVE_ITEMS가 들고 있고(ready/auto), 여기는
        체크 여부로 그 둘 중 하나를 고르기만 한다."""

        page = _page()
        block = _block(page, "async function recommend")

        self.assertIn("have[item.stage] ? item.ready : item.auto", block)

        table = _block(page, "const HAVE_ITEMS", "\n];")
        self.assertIn('auto:"generate"', table)

    def test_it_applies_to_the_stages(self):
        page = _page()
        block = _block(page, "async function recommend")

        self.assertIn("uiPick", block)
        self.assertIn("stagePick", block)

    def test_the_user_can_still_change_it_afterwards(self):
        page = _page()
        block = _block(page, "async function recommend")

        self.assertNotIn("disabled", block)
        self.assertIn('id="stagePicks"', page)

    def test_every_recommended_key_is_a_real_option(self):
        page = _page()
        ui = re.search(r"const STAGE_UI = \{(.*?)\n\};", page, re.S).group(1)
        keys = set(re.findall(r'\{key:"(\w+)"', ui))

        block = _block(page, "const HAVE_ITEMS", "\n];")
        used = set(re.findall(r'(?:ready|auto):"(\w+)"', block))

        self.assertTrue(used)
        for key in used:
            with self.subTest(key=key):
                self.assertIn(key, keys)


class TestTheReason(unittest.TestCase):

    def test_it_is_shown_under_the_button(self):
        page = _page()

        self.assertIn('id="recommendReason"', page)

    def test_it_covers_the_empty_case(self):
        page = _page()
        block = _block(page, "function reasonFor")

        self.assertIn("자료가 없어", block)

    def test_it_names_what_was_prepared(self):
        page = _page()
        block = _block(page, "function reasonFor")

        self.assertIn("준비하셨으므로", block)

    def test_it_stays_one_line(self):
        """설명은 최대 한 줄."""

        page = _page()
        block = _block(page, "function reasonFor")

        self.assertNotIn("<br>", block)
        self.assertNotIn("<p>", block)


class TestTheReadiness(unittest.TestCase):

    def test_the_bar_exists(self):
        page = _page()

        self.assertIn('id="readiness"', page)
        self.assertIn("제작 준비도", page)

    def test_the_rule_is_the_simple_one(self):
        """직접 제공이든 AI 생성이든 준비된 것이다. 아닌 것은 둘뿐 -
        사용 안 함과 맡을 Provider가 없는 경우."""

        page = _page()
        block = _block(page, "function readiness")

        self.assertIn('option.mode !== "none"', block)
        self.assertIn("providers.length === 0", block)

    def test_a_stage_without_a_provider_is_not_ready(self):
        page = _page()
        block = _block(page, "function readiness")

        self.assertIn("providers", block)

    def test_it_makes_no_new_algorithm(self):
        """단순 계산 - 준비된 단계 수를 전체로 나눈다."""

        page = _page()
        block = _block(page, "function readiness")

        self.assertNotIn("Math.pow", block)
        self.assertNotIn("weight", block)
        self.assertIn("length", block)

    def test_each_stage_shows_a_tick(self):
        page = _page()
        block = _block(page, "function renderReadiness")

        self.assertIn("✓", block)


class TestTheGenerateButton(unittest.TestCase):

    def test_it_shows_the_readiness(self):
        page = _page()
        block = _block(page, "function renderReadiness")

        self.assertIn('$("go")', block)
        self.assertIn("준비도", block)

    def test_it_is_never_disabled_by_readiness(self):
        """막지 않는다 - 정보만 준다."""

        page = _page()
        block = _block(page, "function renderReadiness")

        self.assertNotIn("disabled = true", block)
        self.assertNotIn('disabled", true', block)

    def test_it_still_posts_the_same_job(self):
        page = _page()

        self.assertIn('id="go"', page)
        self.assertIn("/studio/api/jobs", page)


class TestTheProviderNamesFold(unittest.TestCase):

    def test_there_is_a_toggle(self):
        page = _page()

        self.assertIn('id="providersToggle"', page)

    def test_it_is_folded_by_default(self):
        page = _page()
        block = _block(page, "function renderCurrentProviders")

        self.assertIn("providersOpen", block)

    def test_folded_shows_the_plain_words(self):
        page = _page()
        block = _block(page, "function renderCurrentProviders")

        self.assertIn("plainLabel", block)

    def test_unfolded_shows_the_real_provider(self):
        page = _page()
        block = _block(page, "function renderCurrentProviders")

        self.assertIn("engine.name", block)


class TestNothingBehindTheScreenMoved(unittest.TestCase):

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_the_pipeline_is_untouched(self):
        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("app.production", name)

    def test_the_resolvers_are_untouched(self):
        from app.steps import (
            step01_script_resolve, step02_asset_resolve, step03_voice_resolve,
        )

        for module in (step01_script_resolve, step02_asset_resolve,
                       step03_voice_resolve):
            for name in self._imports(module):
                with self.subTest(module=module.__name__, imported=name):
                    self.assertNotIn("app.production", name)

    def test_the_plan_contract_is_unchanged(self):
        response = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate"}},
        )

        self.assertEqual(response.status_code, 200)
        for invented in ("readiness", "recommend", "have"):
            with self.subTest(key=invented):
                self.assertNotIn(invented, response.json())

    def test_the_dangling_name_guard_still_holds(self):
        """Sprint119에서 함수를 통째로 지운 사고가 있었다."""

        page = _page()
        script = page[page.index("<script>"):page.rindex("</script>")]

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
