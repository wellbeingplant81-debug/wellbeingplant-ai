"""
Sprint132 - 고를 수 있게 한다 (Epic 56, Phase 9).

Sprint130에 FLUX가, Sprint131에 GPT Image가 실제로 붙었다. 그런데 어느
화면에서도 고를 수 없었다 - 등록소가 둘을 여전히 "향후 지원 예정"으로
들고 있었고, Review에는 음성 Provider 선택기만 있었다. project.json에
직접 적어야만 닿는 상태였다.

이번에는 엔진을 건드리지 않는다. 이미 도는 것을 화면에 연결한다.

두 계층을 구분한다
------------------
    엔진 계층   provider_selection.WIRED - 실제로 만드는 자리
    등록소      app.production - 화면이 목록을 그리는 자리

Sprint131까지 둘이 어긋나 있었다(엔진은 되는데 등록소는 아직이라고
말했다). 이번에 맞춘다.

Coming Soon과 설정 필요는 다르다
--------------------------------
Coming Soon은 "코드가 없다"는 뜻이고 설정 필요는 "코드는 있는데 키가
없다"는 뜻이다. 이제 FLUX와 GPT Image는 뒤쪽이다 - 키를 넣으면 바로
쓸 수 있다. 그래서 못 쓰는 이유로 필요한 설정 이름을 그대로 말한다.

키가 없으면 카드는 보이되 고를 수 없다. Sprint125가 ElevenLabs에
정한 방식과 같다 - 고르게 해 두고 만들 때 실패하는 것보다, 무엇을
넣어야 하는지 그 자리에서 말하는 편이 낫다.

새 API를 만들지 않는다
----------------------
선택은 Sprint126이 만든 PUT /api/review/{project}/providers 하나로
간다. maker 화면도 프로젝트를 만든 직후 같은 곳으로 보낸다.
"""

import ast
import json
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import source_modes, stages
from app.production.providers import bootstrap
from app.production.providers.coming_soon import COMING_SOON
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import ProviderUnavailable
from app.production.stage_request import StageRequest
from app.services import provider_selection

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)

WIRED_IMAGE = ("flux", "gpt_image")
STILL_COMING = ("imagen", "ideogram")


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script():
    page = _page()
    return page[page.index("<script>"):]


def _registry():
    registry = StageProviderRegistry()
    bootstrap.register_current_providers(registry)
    return registry


class TestTheCatalogAgreesWithTheEngine(unittest.TestCase):
    """Sprint131까지 어긋나 있던 것."""

    def setUp(self):
        self.registry = _registry()

    def test_the_wired_ones_are_no_longer_coming_soon(self):
        for name in WIRED_IMAGE:
            with self.subTest(name=name):
                provider = self.registry.get(stages.IMAGE, name)
                self.assertFalse(getattr(provider, "coming_soon", False))

    def test_the_unwired_ones_are_still_coming_soon(self):
        for name in STILL_COMING:
            with self.subTest(name=name):
                provider = self.registry.get(stages.IMAGE, name)
                self.assertTrue(getattr(provider, "coming_soon", False))

    def test_the_table_no_longer_holds_them(self):
        """자리만 있는 것들의 표에서 빠져야 한다 - 두 번 등록되면
        나중 것이 앞의 것을 가린다."""

        names = {entry[0] for entry in COMING_SOON}

        for name in WIRED_IMAGE:
            with self.subTest(name=name):
                self.assertNotIn(name, names)

    def test_every_wired_name_is_in_the_catalog(self):
        """엔진이 아는 것을 화면이 모르면 고를 수 없다."""

        catalog = {p.name for p in self.registry.for_stage(stages.IMAGE)}

        for name in provider_selection.WIRED["image"]:
            with self.subTest(name=name):
                self.assertIn(name, catalog)

    def test_they_are_offered_as_something_that_generates(self):
        for name in WIRED_IMAGE:
            with self.subTest(name=name):
                provider = self.registry.get(stages.IMAGE, name)
                self.assertIn(
                    source_modes.GENERATE,
                    provider.capabilities.supported_source_modes)

    def test_registering_twice_is_safe(self):
        registry = _registry()
        before = len(registry.for_stage(stages.IMAGE))

        bootstrap.register_current_providers(registry)

        self.assertEqual(len(registry.for_stage(stages.IMAGE)), before)


class TestItSaysWhatIsMissing(unittest.TestCase):
    """Coming Soon이 아니라 설정 필요다."""

    def setUp(self):
        self.registry = _registry()

    def _provider(self, name):
        return self.registry.get(stages.IMAGE, name)

    def test_without_a_key_it_is_unavailable_and_says_which(self):
        expected = {"flux": "FLUX_API_KEY", "gpt_image": "OPENAI_API_KEY"}

        with patch.dict(os.environ, {}, clear=True):
            for name, setting in expected.items():
                with self.subTest(name=name):
                    available, reason = self._provider(name).availability()

                    self.assertFalse(available)
                    self.assertIn(setting, reason)

    def test_with_a_key_it_is_available(self):
        for name, setting in (("flux", "FLUX_API_KEY"),
                              ("gpt_image", "OPENAI_API_KEY")):
            with self.subTest(name=name):
                with patch.dict(os.environ, {setting: "k"}, clear=True):
                    available, reason = self._provider(name).availability()

                    self.assertTrue(available)
                    self.assertEqual(reason, "")

    def test_the_required_settings_are_named(self):
        for name, setting in (("flux", "FLUX_API_KEY"),
                              ("gpt_image", "OPENAI_API_KEY")):
            with self.subTest(name=name):
                self.assertIn(
                    setting,
                    self._provider(name).capabilities.required_settings)

    def test_it_refuses_to_generate_without_a_key(self):
        with patch.dict(os.environ, {}, clear=True):
            for name in WIRED_IMAGE:
                with self.subTest(name=name):
                    with self.assertRaises(ProviderUnavailable):
                        self._provider(name).generate(StageRequest(
                            project_path="x", scenes=[{"scene": 1}]))

    def test_a_vendor_and_a_name_are_there_for_the_screen(self):
        for name in WIRED_IMAGE:
            with self.subTest(name=name):
                capabilities = self._provider(name).capabilities

                self.assertTrue(capabilities.display_name)
                self.assertTrue(capabilities.vendor)

    def test_the_price_is_still_unknown(self):
        """재 본 적이 없다. 모르는 것은 비워 둔다."""

        for name in WIRED_IMAGE:
            with self.subTest(name=name):
                self.assertIsNone(
                    self._provider(name).capabilities.estimated_cost)


class TestItReachesTheSameProviderTheBridgeUses(unittest.TestCase):
    """등록소의 것과 다리의 것이 다른 자리면 결과가 갈린다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name
        self.registry = _registry()

    def _scenes(self):
        return [{"scene": n, "image_prompt": f"p{n}"} for n in (1, 2)]

    def test_flux_goes_to_the_flux_module(self):
        from app.providers import flux_provider

        with patch.dict(os.environ, {"FLUX_API_KEY": "k"}, clear=True):
            with patch.object(flux_provider, "generate_image") as generate:
                self.registry.get(stages.IMAGE, "flux").generate(
                    StageRequest(project_path=self.project,
                                 scenes=self._scenes()))

        self.assertEqual(generate.call_count, 2)

    def test_gpt_image_goes_to_the_gpt_image_module(self):
        from app.providers import gpt_image_provider

        with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}, clear=True):
            with patch.object(gpt_image_provider,
                              "generate_image") as generate:
                self.registry.get(stages.IMAGE, "gpt_image").generate(
                    StageRequest(project_path=self.project,
                                 scenes=self._scenes()))

        self.assertEqual(generate.call_count, 2)

    def test_it_writes_where_the_engine_writes(self):
        from app.providers import flux_provider

        with patch.dict(os.environ, {"FLUX_API_KEY": "k"}, clear=True):
            with patch.object(flux_provider, "generate_image") as generate:
                result = self.registry.get(stages.IMAGE, "flux").generate(
                    StageRequest(project_path=self.project,
                                 scenes=self._scenes()))

        written = [call.args[1] for call in generate.call_args_list]

        self.assertEqual(
            [os.path.basename(p) for p in written],
            ["scene1.png", "scene2.png"])
        self.assertEqual(len(result["images"]), 2)

    def test_it_needs_scenes(self):
        with patch.dict(os.environ, {"FLUX_API_KEY": "k"}, clear=True):
            with self.assertRaises(ValueError):
                self.registry.get(stages.IMAGE, "flux").generate(
                    StageRequest(project_path=self.project))


class TestTheExistingEndpointCarriesTheChoice(unittest.TestCase):
    """새 API를 만들지 않는다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = self._tmp.name

    def _put(self, providers):
        from fastapi.testclient import TestClient

        import app.routers.studio as studio_router
        from app.main import app

        with patch.object(studio_router, "_project_path",
                          lambda project_id: self.project):
            return TestClient(app).put(
                "/studio/api/review/p1/providers",
                json={"providers": providers})

    def _saved(self):
        path = os.path.join(self.project, "project.json")

        if not os.path.exists(path):
            return {}

        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_choosing_flux_lands_in_project_json(self):
        response = self._put({"image": "flux"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._saved().get("image_provider"), "flux")

    def test_choosing_gpt_image_lands_in_project_json(self):
        self._put({"image": "gpt_image"})

        self.assertEqual(self._saved().get("image_provider"), "gpt_image")

    def test_what_the_engine_reads_is_the_chosen_one(self):
        for name in WIRED_IMAGE:
            with self.subTest(name=name):
                self._put({"image": name})

                self.assertEqual(
                    provider_selection.selected(self.project, "image"), name)

    def test_current_folds_back_to_the_existing_path(self):
        self._put({"image": "flux"})
        self._put({"image": "current"})

        self.assertIsNone(
            provider_selection.selected(self.project, "image"))

    def test_choosing_an_image_provider_does_not_move_the_others(self):
        self._put({"voice": "elevenlabs"})
        self._put({"image": "flux"})

        saved = self._saved()

        self.assertEqual(saved.get("voice_provider"), "elevenlabs")
        self.assertEqual(saved.get("image_provider"), "flux")


class TestTheReviewScreenOffersIt(unittest.TestCase):

    def test_one_picker_serves_every_stage(self):
        """음성용을 복제하면 두 자리가 조금씩 갈라진다."""

        self.assertIn("function reviewProviders(", _script())

    def test_the_image_step_shows_it(self):
        self.assertRegex(
            _script(), r'reviewProviders\(\s*state\s*,\s*"image"')

    def test_the_voice_step_still_shows_it(self):
        self.assertRegex(
            _script(), r'reviewProviders\(\s*state\s*,\s*"voice"')

    def test_choosing_goes_to_the_existing_endpoint(self):
        script = _script()

        self.assertIn("function reviewPickProvider(", script)
        self.assertRegex(script, r'reviewCall\("PUT",\s*"/providers"')

    def test_the_old_voice_only_names_are_gone(self):
        """남겨 두면 어느 쪽이 도는지 알 수 없다."""

        script = _script()

        self.assertNotIn("reviewVoiceProviders", script)
        self.assertNotIn("reviewPickVoiceProvider", script)


class TestTheMakerScreenOffersIt(unittest.TestCase):

    def test_there_is_a_provider_picker(self):
        self.assertIn("function stageProviderPicker(", _script())

    def test_it_is_drawn_with_the_stage(self):
        self.assertRegex(_script(), r"stageProviderPicker\(stage,\s*spec\)")

    def test_choosing_is_remembered(self):
        script = _script()

        self.assertIn("function pickProvider(", script)
        self.assertRegex(script, r"uiProvider\[stage\]\s*=")

    def test_current_is_one_of_the_choices(self):
        """고르지 않은 것과 같은 값이 목록에 있어야 되돌릴 수 있다."""

        script = _script()
        start = script.index("function stageProviderPicker(")

        self.assertIn('"current"', script[start:start + 1200])

    def test_coming_soon_ones_are_not_offered(self):
        """아직 코드가 없는 것을 고르게 하면 되는 척이 된다."""

        script = _script()
        start = script.index("function generateProviders(")

        self.assertIn("!p.coming_soon", script[start:start + 400])

    def test_both_pickers_ask_the_same_helper(self):
        """maker와 Review가 다른 목록을 그리면 화면이 갈린다."""

        script = _script()

        for name in ("stageProviderPicker", "reviewProviders"):
            with self.subTest(name=name):
                start = script.index(f"function {name}(")

                self.assertIn("generateProviders(spec)",
                              script[start:start + 900])

    def test_the_choice_travels_when_the_project_is_made(self):
        """
        Sprint139 - 적는 일이 함수 하나로 옮겨졌다. 검토 경로와 영상
        생성 경로가 같은 것을 쓰므로 한쪽만 고쳐지는 일이 없다.
        """

        script = _script()
        start = script.index("async function startReview(")
        body = script[start:start + 900]

        self.assertIn("saveMakerProviders", body)

        start = script.index("async function saveMakerProviders(")
        writer = script[start:start + 400]

        self.assertIn("uiProvider", writer)
        self.assertIn("/providers", writer)


class TestNothingElseMoved(unittest.TestCase):

    def test_no_new_api_path_was_invented(self):
        """선택은 기존 엔드포인트 하나로만 간다."""

        paths = set(re.findall(r'"/studio/api/review[^"`]*"', _page()))

        self.assertEqual(paths, {'"/studio/api/review"'})

    def test_the_engine_layer_did_not_change(self):
        self.assertEqual(
            set(provider_selection.WIRED["image"]), set(WIRED_IMAGE))

    def test_the_bridge_was_not_touched(self):
        from app.services import asset_integration_service

        self.assertEqual(
            set(asset_integration_service.SINGLE_IMAGE_PROVIDERS),
            set(WIRED_IMAGE))

    def test_the_pipeline_and_resolver_do_not_know_these_names(self):
        import app.pipeline.pipeline as pipeline
        from app.steps import step02_asset_resolve, step02_assets

        for module in (pipeline, step02_asset_resolve, step02_assets):
            with open(module.__file__, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            constants = {
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
            }

            for name in WIRED_IMAGE:
                with self.subTest(module=module.__name__, name=name):
                    self.assertNotIn(name, constants)


if __name__ == "__main__":
    unittest.main()
