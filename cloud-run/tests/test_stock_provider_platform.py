"""
Sprint140 - 현재 이미지 엔진이 안에서 쓰는 곳을 드러낸다
(Epic 56, Phase 17).

Sprint138에서 인증을 실제와 맞추면서 하나가 남았다. 이미지의 현재
엔진은 Vertex AI ADC로 Imagen을 부르지만, 그것만으로 도는 것이
아니다 - 스톡 검색도 함께 쓰고 그쪽은 다른 키가 필요하다. 화면에
담을 자리가 없어 적지 못했다.

이번에는 등록과 표시만 한다. 동작은 한 줄도 바꾸지 않는다.

코드에서 확인한 것
------------------
provider_factory.build_provider_chain이 순서를 정한다.

    allow_video=True    pexels_video -> pexels_image
                        -> pixabay_video -> pixabay_image
    allow_video=False   pexels_image -> pixabay_image

두 곳이다 - Pexels와 Pixabay. 각각 동영상과 사진을 찾는다.

    PEXELS_API_KEY      pexels_provider.has_api_key()
    PIXABAY_API_KEY     pixabay_provider.has_api_key()

"폴백"이라고만 적으면 사실이 아니다
-----------------------------------
asset_integration_service를 보면 순서가 scene마다 다르다.

    visual_type == "real"   스톡을 먼저 본다. 실패하면 Imagen
    visual_type == "ai"     Imagen을 먼저 본다. 실패하면 스톡
    visual_type 없음        스톡을 먼저 본다(품질 게이트가 판단)

셋 중 둘에서 스톡이 먼저다. 그래서 화면에는 "폴백"이 아니라 함께
쓰는 곳이라고 적고, 순서가 scene에 달렸다는 사실을 한 줄로 덧붙인다.

단계 Provider로 고를 수 있게 하지 않는다
----------------------------------------
이것들은 current의 대안이 아니라 current 안에서 쓰이는 곳이다.
등록소의 IMAGE 단계에 GENERATE로 올리면 화면이 "Imagen 대신 Pexels"를
고르게 만들고, 그러면 이번 스프린트가 금지한 동작 변경이 된다.

그래서 자리는 만들되 등록소에는 올리지 않는다. 현재 이미지 엔진의
metadata(secondary_providers)에 매달아 화면이 그것을 읽는다 - 같은
사실을 두 곳에서 관리하지 않는다.
"""

import ast
import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import source_modes, stages
from app.production.providers import bootstrap, stock_image
from app.production.registry import StageProviderRegistry

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)

PEXELS = "PEXELS_API_KEY"
PIXABAY = "PIXABAY_API_KEY"


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script():
    page = _page()
    return page[page.index("<script>"):]


def _function(name):
    script = _script()
    block = script[script.index(f"function {name}("):]
    end = block.find("\nfunction ", 1)

    return block if end < 0 else block[:end]


def _registry():
    registry = StageProviderRegistry()
    bootstrap.register_current_providers(registry)
    return registry


class TestTheNamesComeFromTheCode(unittest.TestCase):
    """적어 둔 것이 실제 체인과 같아야 한다."""

    def test_there_are_exactly_the_two_the_chain_uses(self):
        from app.services.provider_factory import build_provider_chain

        vendors = {source.split("_")[0]
                   for source, _ in build_provider_chain(allow_video=True)}

        self.assertEqual(
            {p.name for p in stock_image.stock_image_providers()}, vendors)

    def test_the_key_names_are_the_ones_the_engine_reads(self):
        from app.providers import pexels_provider, pixabay_provider

        expected = {}

        for module, name in ((pexels_provider, "pexels"),
                             (pixabay_provider, "pixabay")):
            with open(module.__file__, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            found = {
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.endswith("_API_KEY")
            }
            expected[name] = found

        for provider in stock_image.stock_image_providers():
            with self.subTest(name=provider.name):
                self.assertEqual(
                    set(provider.capabilities.required_settings),
                    expected[provider.name])

    def test_each_one_names_its_vendor_and_label(self):
        for provider in stock_image.stock_image_providers():
            with self.subTest(name=provider.name):
                self.assertTrue(provider.capabilities.display_name)
                self.assertTrue(provider.capabilities.vendor)

    def test_the_price_is_still_unknown(self):
        for provider in stock_image.stock_image_providers():
            with self.subTest(name=provider.name):
                self.assertIsNone(provider.capabilities.estimated_cost)

    def test_availability_follows_the_key(self):
        for provider in stock_image.stock_image_providers():
            setting = provider.capabilities.required_settings[0]

            with self.subTest(name=provider.name):
                with patch.dict(os.environ, {}, clear=True):
                    available, reason = provider.availability()
                    self.assertFalse(available)
                    self.assertIn(setting, reason)

                with patch.dict(os.environ, {setting: "k"}, clear=True):
                    self.assertTrue(provider.availability()[0])


class TestTheyAreNotStageAlternatives(unittest.TestCase):
    """current의 대안이 아니라 current 안에서 쓰이는 곳이다."""

    def setUp(self):
        self.registry = _registry()

    def test_they_are_not_in_the_image_stage(self):
        names = {p.name for p in self.registry.for_stage(stages.IMAGE)}

        for name in ("pexels", "pixabay"):
            with self.subTest(name=name):
                self.assertNotIn(name, names)

    def test_the_selectable_list_did_not_grow(self):
        """
        이 Sprint가 등록한 것들 때문에 고를 것이 늘지 않았다.

        Sprint150까지는 목록 전체를 적어 두었다. 그 뒤로 다른 Sprint가
        제 Provider를 붙이므로 목록을 통째로 못 박으면 여기가 남의
        Sprint를 막는 자리가 된다 - 지킬 것은 "스톡이 단계 선택지로
        올라오지 않았다"이므로 그것만 본다.
        """

        usable = sorted(
            p.name for p in self.registry.available(
                stages.IMAGE, source_modes.GENERATE)
            if not getattr(p, "coming_soon", False)
        )

        for name in ("pexels", "pixabay"):
            with self.subTest(name=name):
                self.assertNotIn(name, usable)

        # 이 Sprint 전에 있던 것들은 그대로 있다.
        self.assertLessEqual({"current", "flux", "gpt_image"}, set(usable))

    def test_calling_one_as_a_stage_provider_is_refused(self):
        from app.production.stage_provider import ProviderUnavailable
        from app.production.stage_request import StageRequest

        with patch.dict(os.environ, {PEXELS: "k", PIXABAY: "k"}, clear=True):
            for provider in stock_image.stock_image_providers():
                with self.subTest(name=provider.name):
                    with self.assertRaises(ProviderUnavailable):
                        provider.generate(StageRequest(scenes=[{"scene": 1}]))

    def test_the_engine_layer_does_not_import_them(self):
        """등록소가 엔진을 부르지 않는다 - 엔진이 제 모듈을 그대로 쓴다."""

        from app.services import asset_selector, provider_factory

        for module in (asset_selector, provider_factory):
            with open(module.__file__, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names.add(node.module or "")

            for name in names:
                with self.subTest(module=module.__name__, imported=name):
                    self.assertNotIn("app.production", name)


class TestTheCurrentImageEngineCarriesThem(unittest.TestCase):

    def setUp(self):
        self.registry = _registry()

    def _caps(self, stage):
        return self.registry.get(stage, "current").capabilities

    def test_the_capability_has_a_place_for_them(self):
        from app.production import stage_provider

        caps = stage_provider.ProviderCapabilities(name="x", stage="image")

        self.assertEqual(caps.secondary_providers, ())

    def test_the_image_engine_lists_both(self):
        names = {c.name for c in self._caps(stages.IMAGE).secondary_providers}

        self.assertEqual(names, {"pexels", "pixabay"})

    def test_the_primary_authentication_did_not_change(self):
        """Sprint138이 적어 둔 것 그대로다."""

        self.assertEqual(
            self._caps(stages.IMAGE).authentication, "Vertex AI ADC")

    def test_the_other_stages_have_none(self):
        for stage in (stages.SCRIPT, stages.VOICE, stages.METADATA):
            with self.subTest(stage=stage):
                self.assertEqual(self._caps(stage).secondary_providers, ())

    def test_the_facts_live_in_one_place(self):
        """같은 사실을 두 곳에서 관리하지 않는다."""

        from app.production.providers import current_engine

        with open(current_engine.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        constants = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

        for name in (PEXELS, PIXABAY, "pexels", "pixabay"):
            with self.subTest(name=name):
                self.assertNotIn(name, constants)


class TestTheRouterCarriesThem(unittest.TestCase):

    def _row(self, stage="image"):
        from fastapi.testclient import TestClient

        from app.main import app

        payload = TestClient(app).get(
            "/studio/api/production/stages").json()

        return next(s for s in payload["stages"] if s["stage"] == stage)

    def _current(self, stage="image"):
        return [p for p in self._row(stage)["provider_list"]
                if p["name"] == "current"][0]

    def test_every_row_has_the_field(self):
        for stage in ("script", "image", "voice"):
            for provider in self._row(stage)["provider_list"]:
                with self.subTest(stage=stage, provider=provider["name"]):
                    self.assertIn("secondary_providers", provider)

    def test_the_image_current_row_lists_both(self):
        found = self._current()["secondary_providers"]

        self.assertEqual({s["name"] for s in found}, {"pexels", "pixabay"})

    def test_each_one_carries_what_the_screen_needs(self):
        for entry in self._current()["secondary_providers"]:
            with self.subTest(name=entry["name"]):
                for key in ("display_name", "vendor", "authentication",
                            "required_settings"):
                    self.assertIn(key, entry)

    def test_the_key_names_reach_the_screen(self):
        settings = {
            name
            for entry in self._current()["secondary_providers"]
            for name in entry["required_settings"]
        }

        self.assertEqual(settings, {PEXELS, PIXABAY})

    def test_the_script_current_row_has_none(self):
        self.assertEqual(self._current("script")["secondary_providers"], [])


class TestTheScreenShowsThem(unittest.TestCase):

    def test_there_is_one_function_that_words_it(self):
        self.assertIn("function providerExtraAuth(", _script())

    def test_it_reads_the_field_and_nothing_else(self):
        block = _function("providerExtraAuth")

        self.assertIn("secondary_providers", block)
        self.assertNotIn(PEXELS, block)
        self.assertNotIn(PIXABAY, block)

    def test_the_card_shows_them(self):
        self.assertIn("providerExtraAuth", _function("providerCard"))

    def test_the_compare_table_shows_them(self):
        self.assertIn("providerExtraAuth", _function("providerCompare"))

    def test_the_order_fact_reaches_the_screen(self):
        """
        셋 중 둘에서 스톡이 먼저다. "폴백"이라고만 적으면 사실이 아니므로
        순서가 scene에 달렸다는 사실을 함께 내보낸다.
        """

        from app.production.providers.stock_image import ORDER_NOTE

        self.assertIn("visual_type", ORDER_NOTE)

        block = _function("providerCard")

        self.assertIn("chosen.note", block)

    def test_the_screen_does_not_word_the_order_itself(self):
        """순서는 코드가 아는 사실이다 - 화면이 지어내지 않는다."""

        script = _script()

        self.assertNotIn("visual_type", script)

    def test_nothing_is_hardcoded_in_the_page(self):
        page = _page()

        for name in (PEXELS, PIXABAY):
            with self.subTest(name=name):
                self.assertNotIn(name, page)


class TestNothingBelowMoved(unittest.TestCase):
    """동작은 한 줄도 바꾸지 않는다."""

    def _source(self, module):
        with open(module.__file__, encoding="utf-8") as f:
            return f.read()

    def test_the_chain_order_is_untouched(self):
        from app.services.provider_factory import build_provider_chain

        self.assertEqual(
            [source for source, _ in build_provider_chain(allow_video=True)],
            ["pexels_video", "pexels_image", "pixabay_video",
             "pixabay_image"])
        self.assertEqual(
            [source for source, _ in build_provider_chain(allow_video=False)],
            ["pexels_image", "pixabay_image"])

    def test_the_engine_files_did_not_learn_a_new_word(self):
        from app.services import (
            asset_integration_service, asset_selector, best_of_n_service,
            provider_factory,
        )

        for module in (asset_selector, provider_factory, best_of_n_service,
                       asset_integration_service):
            with self.subTest(module=module.__name__):
                self.assertNotIn(
                    "secondary_providers", self._source(module))

    def test_the_resolver_and_step_did_not_change(self):
        """
        step02_assets는 원래 스톡을 안다 - 그것이 이미지 엔진이다.
        이번에 더한 말(secondary_providers)이 스며들지 않았는지 본다.
        """

        from app.steps import step02_asset_resolve, step02_assets

        for module in (step02_asset_resolve, step02_assets):
            with self.subTest(module=module.__name__):
                self.assertNotIn(
                    "secondary_providers", self._source(module))


class TestTheHandlersStillLineUp(unittest.TestCase):

    def test_every_handler_the_markup_calls_is_declared(self):
        page = _page()
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(r'on(?:click|change)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
