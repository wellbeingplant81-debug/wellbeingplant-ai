"""
Sprint120 - 무엇을 가지고 있는지 묻는다 (Epic 54, Phase 19).

Sprint119는 예산으로 물었다("500원 이하"). 그런데 그 금액은 우리가
계산할 수 없는 값이었다 - 어느 Provider도 단가를 신고하지 않아서
카드가 목표라고 적어 두는 수밖에 없었다.

이번에는 사용자가 실제로 아는 것만 묻는다. 대본이 있는가, 이미지가
있는가, 목소리를 직접 쓸 것인가. 전부 사용자가 답을 아는 사실이고,
그 답이 곧 어느 단계를 AI에게 맡길지를 정한다. 화면이 모르는 것을
묻지 않게 됐다.

다섯 답은 누적이다 - "이미지'도' 있습니다"가 대본을 이미 가진 상태에서
쌓이는 말이기 때문이다. 그래서 자동화 비율이 100 / 75 / 50 / 25 / 0으로
떨어진다.

    자료가 아무것도 없습니다    대본 AI · 이미지 AI · 음성 AI
    대본은 이미 있습니다        대본 직접 · 이미지 AI · 음성 AI
    이미지도 있습니다           대본 직접 · 이미지 직접 · 음성 AI
    내 목소리를 사용할 겁니다   대본 직접 · 이미지 직접 · 음성 직접
    전부 직접 만들었습니다      메타데이터까지 직접
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


class TestTheRadioAnswersBecameCheckboxes(unittest.TestCase):
    """Sprint120(UX 6.0) - 라디오 하나로 다섯 상황 중 하나를 고르게 하던
    것을 체크박스 넷으로 바꿨다.

    라디오는 "대본은 있는데 음성만 없다" 같은 조합을 표현할 수 없었다.
    가진 것은 서로 독립이다. 새 화면은 test_studio_ux7이 본다."""

    def test_the_checkboxes_took_their_place(self):
        page = _page()

        self.assertNotIn("const SITUATIONS", page)
        self.assertIn("const HAVE_ITEMS", page)
        self.assertIn("이미 준비된 자료가 있나요?", page)

    def test_the_budget_wording_is_still_gone(self):
        page = _page()
        visible = re.sub(r"^\s*//.*$", "", page, flags=re.M)
        visible = re.sub(r"/\*.*?\*/", "", visible, flags=re.S)

        for wording in ("500원", "1000원", "목표 0원", "제한 없음"):
            with self.subTest(wording=wording):
                self.assertNotIn(wording, visible)


class TestTheNextButton(unittest.TestCase):

    def test_it_exists(self):
        page = _page()

        self.assertIn('id="toDetail"', page)
        self.assertIn("다음", page)

    def test_the_detail_is_closed_until_it_is_pressed(self):
        page = _page()
        block = page[page.index('id="detailStep"'):][:220]

        self.assertIn("display:none", block)

    def test_pressing_it_opens_the_detail(self):
        page = _page()
        block = _block(page, "function showDetail")

        self.assertIn("detailStep", block)

    def test_you_can_go_back_to_the_question(self):
        page = _page()

        self.assertIn("backToSituation", page)

    def test_the_plan_is_computed_before_the_next_button(self):
        """[다음]을 누르기 전에도 요약이 무엇을 만들지 말해 준다."""

        page = _page()
        block = _block(page, "async function recommend")

        self.assertIn("refreshPlan", block)


class TestTheAnswerOnlySetsDefaults(unittest.TestCase):

    def test_it_does_not_lock_the_stages(self):
        page = _page()
        block = _block(page, "async function recommend")

        self.assertIn("uiPick", block)
        self.assertNotIn("disabled", block)

    def test_the_stage_cards_are_still_there(self):
        page = _page()

        self.assertIn('id="stagePicks"', page)
        self.assertIn('id="advanced"', page)


class TestTheSummaryStillTellsTheTruth(unittest.TestCase):
    """Sprint117~119가 세운 것들이 그대로여야 한다."""

    def test_the_expected_result_card_survives(self):
        page = _page()
        block = _block(page, "function expectedResult")

        # Sprint137 - "제작속도"는 등급으로 읽힌다. 잰 것은 시간이므로
        # 시간이라고 적는다.
        for label in ("품질", "제작시간", "비용", "자동화"):
            with self.subTest(label=label):
                self.assertIn(label, block)

    def test_the_cost_rating_still_says_it_is_not_money(self):
        """Sprint137 - 별을 걷으면서 이유를 더 분명히 적었다."""

        page = _page()
        block = _block(page, "function expectedResult")

        self.assertIn("단가", block)

    def test_the_cost_wording_still_has_the_states(self):
        page = _page()
        block = _block(page, "function costWording")

        # Sprint168 - 문구만 바뀌었다. 지킬 것은 그대로다.
        self.assertIn("NO_COST", block)
        self.assertIn('const NO_COST = "API 비용 없음"', page)

        for wording in ("계산 불가",):
            with self.subTest(wording=wording):
                self.assertIn(wording, block)

    def test_metadata_still_reaches_the_plan(self):
        plan = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate", "image": "generate",
                                 "voice": "generate", "metadata": "generate",
                                 "music": "generate"}},
        ).json()

        self.assertIn("metadata", plan["stages"])


class TestTheScriptHasNoDanglingNames(unittest.TestCase):
    """이번 스프린트에서 실제로 낸 사고를 막는 가드다.

    화면을 고쳐 넣다가 교체 범위를 넓게 잡아 상수 둘과 함수 여섯을
    통째로 지웠다. 서버 테스트는 문자열만 보므로 거의 다 통과했고,
    브라우저에서만 죽었을 것이다.

    문법을 다 검사하지는 않는다 - 부르는데 선언이 없는 이름만 본다.
    그것이 이번에 난 사고의 모양이다."""

    def _script(self):
        page = _page()
        return page[page.index("<script>"):page.rindex("</script>")]

    def test_every_handler_the_markup_calls_is_declared(self):
        """onclick/onchange가 가리키는 함수가 없으면 버튼이 죽는다."""

        page = _page()
        script = self._script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])

    def test_every_constant_that_is_used_is_declared(self):
        """상수를 지우면 그것을 쓰는 자리에서 화면이 죽는다.

        ALL_CAPS 뒤에 점이나 대괄호가 오는 자리만 본다 - 화면 글에
        들어 있는 대문자 낱말(API, HIT 같은 것)까지 세면 가드가
        스스로 못 쓰게 된다.

        Sprint155 - 주석 줄은 먼저 걷어낸다. 코드를 보는 가드인데
        주석을 읽으면, 설명에 "POST .../library"라고 적은 것만으로
        선언되지 않은 상수를 쓴 것처럼 걸린다(실제로 걸렸다). 이
        저장소가 여러 번 겪은 모양이다.

        줄 전체가 주석인 것만 지운다 - 코드 줄 뒤에 붙은 "// ..."까지
        지우면 "https://"가 든 문자열이 잘려 그 줄의 진짜 쓰임을
        놓칠 수 있다."""

        script = re.sub(r"(?m)^[ \t]*//.*$", "", self._script())

        declared = set(re.findall(r"const\s+([A-Z][A-Z0-9_]+)\s*=", script))
        # 브라우저가 주는 전역.
        declared.add("JSON")
        used = set(re.findall(r"(?<![\w.$])([A-Z][A-Z0-9_]{2,})\s*[.\[]",
                              script))

        self.assertTrue(used)
        self.assertEqual(sorted(used - declared), [])

    def test_the_constants_this_sprint_deleted_are_back(self):
        script = self._script()

        # Sprint137 - STARS는 이번에 뜻이 있어서 지웠다. 사고로
        # 사라진 것이 아니므로 이 가드에서 뺀다.
        for name in ("HIDDEN_STAGES", "API_MODES", "BASIC_STAGES",
                     "ADVANCED_STAGES", "STAGE_UI", "HAVE_ITEMS"):
            with self.subTest(name=name):
                self.assertIn("const " + name, script)

    def test_the_helpers_this_sprint_deleted_are_back(self):
        script = self._script()

        for name in ("stageLabel", "optionOf", "plainLabel",
                     "cardKind", "stageSummary"):
            with self.subTest(name=name):
                self.assertIn("function " + name, script)


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
        for invented in ("situation", "preset", "budget"):
            with self.subTest(key=invented):
                self.assertNotIn(invented, response.json())

    def test_the_generate_button_still_posts_the_same_job(self):
        page = _page()

        self.assertIn('id="go"', page)
        self.assertIn("/studio/api/jobs", page)


if __name__ == "__main__":
    unittest.main()
