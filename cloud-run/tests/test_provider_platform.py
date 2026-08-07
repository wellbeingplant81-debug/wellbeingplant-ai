"""
Sprint124 - Provider를 고를 수 있는 자리를 만든다 (Epic 56, Phase 1).

지금까지 단계마다 Provider는 하나뿐이었다("current"). 그래서 화면이
"어떤 AI를 쓸까"를 물을 수 없었다. 이번에는 자리를 만든다 - 실제
API는 하나도 붙이지 않는다.

붙이지 않았다는 것을 화면과 코드가 똑같이 말해야 한다.

    generate()  ProviderUnavailable - 되는 척하지 않는다
    화면        Coming Soon · 선택 불가

지어내지 않는 것 둘
-------------------
비용. estimated_cost 필드는 만들되 값은 None이다. 우리는 이 Provider들의
단가를 모른다. Sprint117부터 이 저장소는 모르면 "단가 미상"으로 적어
왔고, Sprint119에서 금액을 목표로만 쓰다가 Sprint120에서 아예 걷어냈다.
숫자를 채우는 것은 실제 단가를 받은 뒤의 일이다.

품질. quality_tier는 재 본 것에만 의미가 있다. 아직 부르지도 않은
Provider를 ★★★★★로 매기는 것은 지어내는 일이다. 그래서 전부
STANDARD로 두고, 화면은 쓸 수 없는 Provider에 별 대신 "미측정"을
적는다.

겹치는 이름에 대해
------------------
현재 엔진은 이미 gemini-2.5-pro / imagen-4.0 / Chirp3-HD를 쓴다.
그러니 "Gemini"·"Imagen"·"Google TTS"를 따로 등록하는 것은 같은 것을
두 번 적는 것처럼 보인다. 다른 점은 하나다 - current는 이 저장소의
파이프라인(Duration Gate·Viral Writer·품질 게이트)을 거치고, 그것들은
모델을 직접 부르는 자리다. 아직 그 자리가 비어 있으므로 화면이
그 사실을 적는다.
"""

import ast
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import source_modes, stage_provider, stages
from app.production.providers import bootstrap
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import (
    ProviderUnavailable, StageProviderError,
)
from app.production.stage_request import StageRequest


def _registry():
    registry = StageProviderRegistry()
    bootstrap.register_current_providers(registry)
    return registry


class TestTheCapabilitiesGrew(unittest.TestCase):

    def test_the_new_fields_exist(self):
        caps = stage_provider.ProviderCapabilities(name="x", stage="script")

        for field in ("display_name", "vendor", "estimated_cost",
                      "supports_streaming"):
            with self.subTest(field=field):
                self.assertTrue(hasattr(caps, field))

    def test_the_three_supports_are_derived_not_stored(self):
        """supported_source_modes와 따로 적어 두면 한쪽만 바뀐다."""

        caps = stage_provider.ProviderCapabilities(
            name="x", stage="script",
            supported_source_modes=(source_modes.IMPORT, source_modes.MANUAL),
        )

        self.assertFalse(caps.supports_generate)
        self.assertTrue(caps.supports_import)
        self.assertTrue(caps.supports_manual)

    def test_the_label_falls_back_to_the_name(self):
        caps = stage_provider.ProviderCapabilities(name="current", stage="script")

        self.assertEqual(caps.label, "current")

    def test_streaming_is_off_unless_declared(self):
        caps = stage_provider.ProviderCapabilities(name="x", stage="script")

        self.assertFalse(caps.supports_streaming)

    def test_the_cost_is_unknown_by_default(self):
        """0.0과 None은 다르다 - 0.0은 무료임을 안다는 뜻이다."""

        caps = stage_provider.ProviderCapabilities(name="x", stage="script")

        self.assertIsNone(caps.estimated_cost)


class TestTheComingSoonProviders(unittest.TestCase):

    def setUp(self):
        self.registry = _registry()

    def test_the_script_stage_offers_the_named_ones(self):
        names = {p.name for p in self.registry.for_stage(stages.SCRIPT)}

        for name in ("current", "chat_import", "gemini", "claude",
                     "openai", "deepseek"):
            with self.subTest(name=name):
                self.assertIn(name, names)

    def test_the_image_stage_offers_the_named_ones(self):
        names = {p.name for p in self.registry.for_stage(stages.IMAGE)}

        for name in ("current", "image_import", "imagen", "gpt_image",
                     "flux", "ideogram"):
            with self.subTest(name=name):
                self.assertIn(name, names)

    def test_the_voice_stage_offers_the_named_ones(self):
        names = {p.name for p in self.registry.for_stage(stages.VOICE)}

        for name in ("current", "voice_import", "google_tts", "elevenlabs",
                     "openai_voice"):
            with self.subTest(name=name):
                self.assertIn(name, names)

    def test_available_without_a_mode_returns_all_of_them(self):
        every = self.registry.available(stages.SCRIPT)

        self.assertGreaterEqual(len(every), 6)

    def test_each_one_names_its_vendor(self):
        for stage in (stages.SCRIPT, stages.IMAGE, stages.VOICE):
            for provider in self.registry.for_stage(stage):
                if provider.name in ("current", "chat_import",
                                     "image_import", "voice_import"):
                    continue
                with self.subTest(provider=provider.name):
                    self.assertTrue(provider.capabilities.vendor)
                    self.assertTrue(provider.capabilities.display_name)


class TestTheyRefuseHonestly(unittest.TestCase):

    def setUp(self):
        self.registry = _registry()

    def _coming_soon(self):
        found = []
        for stage in stages.STAGES:
            for provider in self.registry.for_stage(stage):
                if getattr(provider, "coming_soon", False):
                    found.append(provider)
        return found

    def test_there_are_some(self):
        """
        Sprint125 ElevenLabs, Sprint132 FLUX·GPT Image가 빠졌다. 셋 다
        엔진이 실제로 붙어서 자리만 있는 쪽이 아니게 됐다.

        수가 줄어드는 것이 이 표의 정상적인 방향이다.
        """

        self.assertGreaterEqual(len(self._coming_soon()), 4)

        names = {p.name for p in self._coming_soon()}

        for wired in ("elevenlabs", "flux", "gpt_image", "gemini", "claude",
                      "openai", "deepseek"):
            with self.subTest(name=wired):
                self.assertNotIn(wired, names)

    def test_generate_raises_provider_unavailable(self):
        for provider in self._coming_soon():
            with self.subTest(provider=provider.name):
                with self.assertRaises(ProviderUnavailable):
                    provider.generate(StageRequest())

    def test_provider_unavailable_is_a_provider_error(self):
        self.assertTrue(issubclass(ProviderUnavailable, StageProviderError))

    def test_the_message_says_it_is_not_wired_yet(self):
        provider = self._coming_soon()[0]

        with self.assertRaises(ProviderUnavailable) as caught:
            provider.generate(StageRequest())

        self.assertIn("아직", str(caught.exception))

    def test_none_of_them_costs_anything_yet(self):
        """단가를 모른다 - 지어내지 않는다."""

        for provider in self._coming_soon():
            with self.subTest(provider=provider.name):
                self.assertIsNone(provider.capabilities.estimated_cost)

    def test_none_of_them_claims_a_quality_ranking(self):
        """부르지도 않은 것을 ★★★★★로 매기지 않는다."""

        tiers = {p.capabilities.quality_tier for p in self._coming_soon()}

        self.assertEqual(tiers, {stage_provider.STANDARD})

    def test_they_say_what_they_would_need(self):
        for provider in self._coming_soon():
            with self.subTest(provider=provider.name):
                self.assertTrue(provider.capabilities.required_settings)

    def test_they_call_no_api(self):
        from app.production.providers import coming_soon

        tree = ast.parse(open(coming_soon.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")

        for forbidden in ("requests", "httpx", "genai", "openai",
                          "anthropic", "elevenlabs"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(any(forbidden in n for n in names), forbidden)


class TestTheCurrentProviderIsUntouched(unittest.TestCase):
    """생성 결과가 바뀌면 안 된다."""

    def test_current_still_exists_for_every_stage_it_had(self):
        registry = _registry()

        for stage in (stages.SCRIPT, stages.IMAGE, stages.VOICE,
                      stages.METADATA):
            with self.subTest(stage=stage):
                self.assertTrue(registry.get(stage, "current"))

    def test_only_the_wired_ones_are_selectable(self):
        """
        Sprint125 음성, Sprint132 이미지. 엔진이 실제로 붙은 것만
        고를 수 있고, 설정이 없으면 스스로 거절한다.

        대본은 아직 현재 엔진뿐이다.
        """

        registry = _registry()

        expected = {
            stages.SCRIPT: ["claude", "current", "deepseek", "gemini",
                            "openai"],
            # Sprint150 - local_stock은 키가 아니라 훑어 둔 폴더가
            # 조건이라 여기 목록에 함께 뜬다.
            stages.IMAGE: ["current", "flux", "gpt_image", "local_stock"],
            # Sprint151 - local_voice도 키가 아니라 훑어 둔 폴더가
            # 조건이라 목록에 함께 뜬다.
            stages.VOICE: ["current", "elevenlabs", "local_voice"],
        }

        for stage, names in expected.items():
            usable = sorted(
                p.name for p in registry.available(stage,
                                                   source_modes.GENERATE)
                if not getattr(p, "coming_soon", False)
            )
            with self.subTest(stage=stage):
                self.assertEqual(usable, names)

    def test_the_current_engine_file_did_not_change(self):
        from app.production.providers import current_engine

        source = open(current_engine.__file__, encoding="utf-8").read()

        for word in ("coming_soon", "ProviderUnavailable", "vendor"):
            with self.subTest(word=word):
                self.assertNotIn(word, source)

    def test_the_engine_steps_are_untouched(self):
        from app.steps import (
            step01_script, step02_assets, step03_tts, step04_subtitle,
            step05_video, step06_thumbnail, step07_quality,
        )

        for module in (step01_script, step02_assets, step03_tts,
                       step04_subtitle, step05_video, step06_thumbnail,
                       step07_quality):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("app.production", source)


class TestTheScreenIsToldTheTruth(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)
        self.rows = {
            r["stage"]: r
            for r in self.client.get(
                "/studio/api/production/stages").json()["stages"]
        }

    def test_the_endpoint_lists_every_provider(self):
        names = {p["name"] for p in self.rows["script"]["provider_list"]}

        for name in ("current", "gemini", "claude", "openai", "deepseek"):
            with self.subTest(name=name):
                self.assertIn(name, names)

    def test_each_row_carries_what_the_card_needs(self):
        for row in self.rows.values():
            for provider in row["provider_list"]:
                with self.subTest(provider=provider["name"]):
                    for key in ("name", "display_name", "vendor",
                                "quality_tier", "estimated_cost",
                                "coming_soon", "required_settings"):
                        self.assertIn(key, provider)

    def test_the_coming_soon_ones_are_flagged(self):
        """
        Sprint141 - 대본 자리는 하나도 남지 않았다. 아직 자리만 있는
        것은 이미지와 음성에 있다.
        """

        imagen = [p for p in self.rows["image"]["provider_list"]
                  if p["name"] == "imagen"][0]

        self.assertTrue(imagen["coming_soon"])
        self.assertIsNone(imagen["estimated_cost"])

    def test_current_is_not_flagged(self):
        current = [p for p in self.rows["script"]["provider_list"]
                   if p["name"] == "current"][0]

        self.assertFalse(current["coming_soon"])

    def test_the_engine_facts_still_name_the_real_models(self):
        self.assertEqual(self.rows["script"]["engine"]["model"],
                         "gemini-2.5-pro")
        self.assertEqual(self.rows["image"]["engine"]["model"],
                         "imagen-4.0-generate-001")


class TestNothingElseMoved(unittest.TestCase):

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

    def test_the_review_workflow_is_untouched(self):
        from app.services import studio_review

        source = open(studio_review.__file__, encoding="utf-8").read()

        self.assertNotIn("app.production", source)

    def test_the_global_registry_stays_empty(self):
        """등록은 명시적으로 부를 때만 일어난다(Sprint103)."""

        from app.production.registry import default_registry

        self.assertEqual(len(default_registry()), 0)


if __name__ == "__main__":
    unittest.main()
