"""
Sprint136 - Provider를 이름 말고 사실로 고른다 (Epic 56, Phase 13).

Sprint132에 화면에서 Provider를 고를 수 있게 됐지만, 목록에 뜨는 것은
이름과 "설정 필요"뿐이었다. 이름만 보고 고르라는 것과 같다.

이번에는 아는 것을 표로 편다. 새로 아는 것은 하나도 없다 - 서버가
이미 보내고 있던 값들로 전부 채워진다. 그래서 서버는 0줄이다.

    이미 오던 값   name · display_name · vendor · source_modes ·
                   coming_soon · available · unavailable_reason ·
                   required_settings · seconds_if_generated
    화면이 잇는 것 Current인가 · 직접 호출인가 · 그 단계 엔진을
                   거치는가 · 실측이 있는가

지어내지 않는다
---------------
별점·빠름·느림·가성비 같은 말은 쓰지 않는다. 재 본 적이 없기 때문이다.
모르는 자리는 "미측정"이라고 적는다.

설명도 의견이 아니라 규칙이다. Provider마다 무엇을 하는지는 이미
정해져 있으므로 그 사실을 그대로 문장으로 바꾼다.

    Current   기존 파이프라인을 사용합니다.
    Direct    선택한 모델을 직접 호출합니다.
    Import    사용자가 제공한 자료를 사용합니다.
    Manual    AI를 호출하지 않습니다.

catalog를 대체한다
------------------
Sprint124의 providerCatalog는 "아직 못 쓰거나 설정이 필요한 것들"만
접어서 보여 줬다. 비교 표는 그것을 포함한 전부를 보여 주므로 같은
것을 두 곳에 두지 않는다.
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

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)

# 재 본 적이 없는 것에 매기는 말들. 화면이 이런 말을 하면 지어내는
# 것이 된다.
BANNED = ("★", "빠름", "느림", "품질 최고", "가성비", "추천", "저렴", "비쌈")

RULES = (
    "기존 파이프라인을 사용합니다.",
    "선택한 모델을 직접 호출합니다.",
    "사용자가 제공한 자료를 사용합니다.",
    "AI를 호출하지 않습니다.",
)

COLUMNS = ("Provider", "만든 곳", "엔진", "상태", "API Key",
           "입력", "그 단계 엔진", "실측")


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script():
    page = _page()
    return page[page.index("<script>"):]


def _function(name):
    """그 함수의 본문만. 다음 function 앞에서 끊는다."""

    script = _script()
    block = script[script.index(f"function {name}("):]

    end = block.find("\nfunction ", 1)

    return block if end < 0 else block[:end]


def _without_comments(block):
    """
    설명을 걷어낸 코드.

    왜 어떤 말을 쓰지 않는지 적어 두려면 그 말을 적어야 한다. 원문을
    훑으면 그 설명 자체가 걸린다 - 이 저장소가 여러 번 겪은 결함이다.
    """

    return re.sub(r"//.*", "", block)


class TestTheCompareTableExists(unittest.TestCase):

    def test_there_is_a_compare_function(self):
        self.assertIn("function providerCompare(", _script())

    def test_it_is_drawn_with_the_stage(self):
        self.assertRegex(_script(), r"\$\{providerCompare\(spec\)\}")

    def test_it_takes_the_place_of_the_partial_catalog(self):
        """같은 것을 두 곳에 두지 않는다 - 부르는 자리도, 그리는 자리도."""

        script = _without_comments(_script())

        self.assertNotIn("providerCatalog", script)
        self.assertNotIn("pcrow", _page())

    def test_every_column_the_sprint_asked_for_is_there(self):
        block = _function("providerCompare")

        for column in COLUMNS:
            with self.subTest(column=column):
                self.assertIn(column, block)

    def test_it_lists_every_provider_not_only_the_broken_ones(self):
        """부분 목록은 못 쓰는 것만 보여 줬다. 비교는 전부 본다."""

        block = _function("providerCompare")

        self.assertIn("const rows = spec.provider_list || []", block)


class TestItDoesNotInventEvaluations(unittest.TestCase):

    def test_no_banned_word_reaches_the_screen(self):
        block = _without_comments(
            _function("providerCompare") + _function("providerMeasured")
            + _function("providerKind") + _function("providerStatus")
            + _function("providerEngineUse"))

        for word in BANNED:
            with self.subTest(word=word):
                self.assertNotIn(word, block)

    def test_it_says_unmeasured_instead(self):
        """Sprint137 - 그 말은 이제 한 곳에서만 적는다."""

        self.assertIn("UNMEASURED", _function("providerMeasured"))
        self.assertIn('const UNMEASURED = "미측정"', _script())

    def test_it_does_not_draw_stars(self):
        block = _without_comments(
            _function("providerCompare") + _function("providerMeasured"))

        self.assertNotIn("starText", block)
        self.assertNotIn("STARS", block)

    def test_the_measured_column_reads_a_measured_number(self):
        """실측이라고 적으려면 잰 값이 있어야 한다."""

        block = _function("providerMeasured")

        self.assertIn("seconds_if_generated", block)
        self.assertIn("providerMeasured", _function("providerCompare"))


class TestTheSentencesAreRulesNotOpinions(unittest.TestCase):

    def test_all_four_rules_are_written(self):
        script = _script()

        for sentence in RULES:
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, script)

    def test_the_rule_is_chosen_by_a_function(self):
        self.assertIn("function providerRule(", _script())

    def test_the_rule_function_invents_nothing(self):
        block = _without_comments(_function("providerRule"))

        for word in BANNED:
            with self.subTest(word=word):
                self.assertNotIn(word, block)


class TestItTellsCurrentFromDirect(unittest.TestCase):

    def test_there_is_a_kind_function(self):
        self.assertIn("function providerKind(", _script())

    def test_both_words_are_used(self):
        block = _function("providerKind")

        self.assertIn("Current", block)
        self.assertIn("Direct", block)

    def test_current_is_decided_by_name_not_by_guessing(self):
        block = _function("providerKind")

        self.assertIn('"current"', block)

    def test_the_pipeline_column_distinguishes_them(self):
        block = _function("providerCompare")

        self.assertIn("providerKind", block)


class TestTheServerDidNotChange(unittest.TestCase):
    """아는 것만 보여 준다 - 새로 알아낸 것이 없으므로 서버도 그대로다."""

    def _payload(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app).get("/studio/api/production/stages").json()

    def test_the_compare_lives_in_the_page_not_the_router(self):
        from app.routers import studio

        with open(studio.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("providerCompare", source)
        self.assertNotIn("providerKind", source)

    def test_the_provider_row_keys_are_the_ones_that_already_existed(self):
        row = next(s for s in self._payload()["stages"]
                   if s["stage"] == "script")

        self.assertEqual(
            set(row["provider_list"][0]),
            {"name", "display_name", "vendor", "quality_tier",
             "estimated_cost", "source_modes", "coming_soon", "available",
             "unavailable_reason", "required_settings", "note"})

    def test_everything_the_table_needs_is_already_sent(self):
        row = next(s for s in self._payload()["stages"]
                   if s["stage"] == "script")

        self.assertIsNotNone(row.get("seconds_if_generated"))

        for provider in row["provider_list"]:
            with self.subTest(provider=provider["name"]):
                for key in ("vendor", "source_modes", "coming_soon",
                            "available", "required_settings"):
                    self.assertIn(key, provider)


class TestNothingBelowTheScreenMoved(unittest.TestCase):
    """Pipeline · Resolver · step01~07 · Provider · Bridge · Review 0줄."""

    def _constants(self, module):
        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_no_engine_module_knows_the_compare_screen(self):
        import app.pipeline.pipeline as pipeline
        from app.services import provider_selection, studio_review
        from app.steps import step01_script, step02_asset_resolve

        for module in (pipeline, provider_selection, studio_review,
                       step01_script, step02_asset_resolve):
            with self.subTest(module=module.__name__):
                constants = self._constants(module)

                self.assertNotIn("providerCompare", constants)
                self.assertNotIn("미측정", constants)

    def test_the_registry_still_reports_what_it_reported(self):
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        for provider in registry.for_stage("script"):
            with self.subTest(provider=provider.name):
                # 등급은 여전히 신고값이고 단가는 여전히 모른다.
                self.assertIsNone(provider.capabilities.estimated_cost)


class TestTheHandlersStillLineUp(unittest.TestCase):
    """지운 이름을 부르는 자리가 남으면 화면이 죽는다."""

    def test_every_handler_the_markup_calls_is_declared(self):
        page = _page()
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])

    def test_no_function_call_points_at_a_deleted_name(self):
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))

        for name in ("providerCompare", "providerKind", "providerRule"):
            with self.subTest(name=name):
                self.assertIn(name, declared)


if __name__ == "__main__":
    unittest.main()
