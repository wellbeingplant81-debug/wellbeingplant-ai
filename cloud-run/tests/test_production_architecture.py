"""
Sprint102 - 제작 플랫폼 아키텍처 (Epic 54, Phase 1).

구조만 세우는 스프린트다. Provider 구현은 하나도 없고 파이프라인은
지금까지 하던 대로 돈다.

그래서 여기서 지키는 것은 "동작"이 아니라 "약속"이다. 특히 둘.

  Auto Premium은 품질이 유일한 기준이다.
    자동화가 곧 저품질이 되는 순간 이 제품의 전제가 무너진다.
    비용 상한이 없다는 것이 그 약속의 코드 표현이다.

  Manual은 API를 부르지 않는다.
    허용 목록에 GENERATE가 없다는 사실 하나에서 유도된다 - 별도
    플래그를 두면 둘이 어긋나는 날이 온다.
"""

import ast
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import (
    cost,
    production_modes,
    production_plan,
    registry,
    source_modes,
    stage_provider,
    stages,
)
from app.production.production_plan import (
    PlanError,
    ProductionPlan,
    StageSelection,
    build_automatic_plan,
)
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import (
    ProviderCapabilities,
    StageProvider,
    StageProviderError,
)


class _Provider(StageProvider):
    """테스트용. 실제 API를 부르지 않는다."""

    def __init__(self, name, stage, tier=stage_provider.STANDARD,
                 modes=(source_modes.GENERATE,), available=True, amount=None):
        self.capabilities = ProviderCapabilities(
            name=name, stage=stage, quality_tier=tier,
            supported_source_modes=tuple(modes),
        )
        self._available = available
        self._amount = amount

    def is_available(self):
        return self._available

    def generate(self, request):
        self._require(source_modes.GENERATE)
        return {"generated": self.name}

    def import_content(self, raw, request=None):
        self._require(source_modes.IMPORT)
        return {"imported": raw}

    def accept_manual(self, payload, request=None):
        self._require(source_modes.MANUAL)
        return {"manual": payload}

    def estimate_cost(self, request, source_mode):
        if self._amount is None:
            return super().estimate_cost(request, source_mode)
        if not source_modes.calls_api(source_mode):
            return super().estimate_cost(request, source_mode)
        return cost.CostEstimate(
            stage=self.stage, provider=self.name, source_mode=source_mode,
            amount=self._amount, unit="영상", quantity=1,
        )


def _full_registry():
    reg = StageProviderRegistry()
    for stage in stages.STAGES:
        reg.register(_Provider(f"{stage}-premium", stage, stage_provider.PREMIUM, amount=1.0))
        reg.register(_Provider(f"{stage}-standard", stage, stage_provider.STANDARD, amount=0.3))
        reg.register(_Provider(f"{stage}-economy", stage, stage_provider.ECONOMY, amount=0.05))
    return reg


class TestStagesAreGroundedInRealArtifacts(unittest.TestCase):
    """단계를 발명하지 않았다 - 파이프라인이 실제로 만드는 것이다."""

    def test_the_artifact_names_match_the_engine(self):
        from app.services.studio_service import MEDIA_KINDS

        self.assertEqual(stages.ARTIFACTS[stages.SCRIPT], "script.json")
        self.assertEqual(
            stages.ARTIFACTS[stages.METADATA], "publish_package.json",
        )
        # 이미지/음성은 studio_service의 판정 경로와 같은 자리다.
        self.assertIn("images", stages.ARTIFACTS[stages.IMAGE])
        self.assertIn("audio", stages.ARTIFACTS[stages.VOICE])
        self.assertIn("thumbnail", MEDIA_KINDS)

    def test_music_has_no_artifact_of_its_own(self):
        """BGM은 최종 영상에 섞여 들어간다 - 없는 산출물을 지어내지
        않는다."""

        self.assertIsNone(stages.ARTIFACTS[stages.MUSIC])

    def test_an_unknown_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            stages.require_stage("subtitle")


class TestAutoPremiumIsQualityFirst(unittest.TestCase):
    """이 제품의 전제다. 자동이 곧 저품질이 되면 안 된다."""

    def test_premium_has_no_cost_ceiling(self):
        self.assertIsNone(
            production_modes.policy_for(production_modes.AUTO_PREMIUM).cost_ceiling,
        )

    def test_premium_prefers_the_highest_quality_tier_first(self):
        preference = production_modes.policy_for(
            production_modes.AUTO_PREMIUM,
        ).quality_preference

        self.assertEqual(preference[0], stage_provider.PREMIUM)

    def test_premium_actually_selects_the_premium_provider(self):
        reg = _full_registry()

        plan = build_automatic_plan(production_modes.AUTO_PREMIUM, reg)

        for stage in stages.STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(
                    plan.selections[stage].provider, f"{stage}-premium",
                )

    def test_premium_picks_quality_even_when_it_costs_the_most(self):
        reg = _full_registry()

        premium = build_automatic_plan(production_modes.AUTO_PREMIUM, reg)
        economy = build_automatic_plan(production_modes.AUTO_ECONOMY, reg)

        self.assertGreater(
            premium.estimate_cost(registry=reg).known_total,
            economy.estimate_cost(registry=reg).known_total,
        )

    def test_only_economy_optimises_for_cost(self):
        """비용을 기준으로 삼는 모드는 하나뿐이다."""

        for mode in (production_modes.AUTO_PREMIUM, production_modes.AUTO_STANDARD):
            with self.subTest(mode=mode):
                self.assertNotEqual(
                    production_modes.policy_for(mode).quality_preference[0],
                    stage_provider.ECONOMY,
                )

        self.assertEqual(
            production_modes.policy_for(
                production_modes.AUTO_ECONOMY).quality_preference[0],
            stage_provider.ECONOMY,
        )

    def test_premium_regenerates_when_quality_falls_short(self):
        self.assertTrue(
            production_modes.policy_for(production_modes.AUTO_PREMIUM).auto_regenerate,
        )

    def test_economy_does_not_regenerate_because_that_is_the_costly_part(self):
        self.assertFalse(
            production_modes.policy_for(production_modes.AUTO_ECONOMY).auto_regenerate,
        )


class TestManualCallsNoApi(unittest.TestCase):

    def test_the_manual_mode_forbids_generation(self):
        allowed = production_modes.policy_for(production_modes.MANUAL).allowed_source_modes

        self.assertNotIn(source_modes.GENERATE, allowed)

    def test_it_is_derived_not_declared_twice(self):
        """별도 플래그를 두지 않는다 - 목록과 플래그가 어긋나는 날이
        온다."""

        self.assertFalse(production_modes.calls_api(production_modes.MANUAL))
        for mode in (production_modes.AUTO_PREMIUM, production_modes.ASSISTED):
            with self.subTest(mode=mode):
                self.assertTrue(production_modes.calls_api(mode))

    def test_a_manual_plan_reports_no_api_stages(self):
        plan = ProductionPlan(mode=production_modes.MANUAL)
        for stage in stages.STAGES:
            plan.select(StageSelection(
                stage=stage, source_mode=source_modes.MANUAL, payload="준 것",
            ))

        self.assertFalse(plan.calls_api)
        self.assertEqual(plan.api_stages, [])

    def test_choosing_generation_in_manual_mode_is_refused(self):
        plan = ProductionPlan(mode=production_modes.MANUAL)

        with self.assertRaises(PlanError) as caught:
            plan.select(StageSelection(
                stage=stages.SCRIPT, source_mode=source_modes.GENERATE,
                provider="x",
            ))

        self.assertIn("쓸 수 없습니다", str(caught.exception))

    def test_an_automatic_plan_cannot_be_built_for_manual(self):
        with self.assertRaises(PlanError):
            build_automatic_plan(production_modes.MANUAL, _full_registry())


class TestChatImportIsAFirstClassPath(unittest.TestCase):
    """GPT/Claude/Gemini/DeepSeek 웹 채팅에서 만들어 붙여넣는 경로.
    출처는 AI지만 우리가 API를 부르지 않으므로 비용이 0이다."""

    def test_import_is_not_billable(self):
        self.assertFalse(source_modes.calls_api(source_modes.IMPORT))
        self.assertIn(source_modes.GENERATE, source_modes.BILLABLE_SOURCE_MODES)

    def test_import_is_allowed_in_assisted_and_manual(self):
        for mode in (production_modes.ASSISTED, production_modes.MANUAL):
            with self.subTest(mode=mode):
                self.assertIn(
                    source_modes.IMPORT,
                    production_modes.policy_for(mode).allowed_source_modes,
                )

    def test_an_imported_stage_costs_nothing(self):
        plan = ProductionPlan(mode=production_modes.ASSISTED)
        plan.select(StageSelection(
            stage=stages.SCRIPT, source_mode=source_modes.IMPORT,
            payload="붙여넣은 대본",
        ))

        estimate = plan.estimate_cost().estimates[0]

        self.assertEqual(estimate.amount, 0.0)
        self.assertTrue(estimate.free)

    def test_a_provider_that_cannot_import_says_so(self):
        provider = _Provider("only-generate", stages.SCRIPT)

        with self.assertRaises(StageProviderError):
            provider.import_content("붙여넣은 텍스트")

    def test_a_provider_that_can_import_receives_the_raw_text(self):
        provider = _Provider(
            "importer", stages.SCRIPT, modes=(source_modes.IMPORT,),
        )

        self.assertEqual(
            provider.import_content("raw"), {"imported": "raw"},
        )


class TestTheProviderContract(unittest.TestCase):

    def test_a_provider_declares_what_it_can_do(self):
        provider = _Provider(
            "p", stages.IMAGE, modes=(source_modes.GENERATE, source_modes.MANUAL),
        )

        self.assertTrue(provider.supports(source_modes.GENERATE))
        self.assertFalse(provider.supports(source_modes.IMPORT))

    def test_an_unsupported_mode_raises_instead_of_returning_nothing(self):
        provider = _Provider("p", stages.IMAGE)

        with self.assertRaises(StageProviderError):
            provider.accept_manual("파일")

    def test_a_misdeclared_provider_is_caught_at_registration(self):
        reg = StageProviderRegistry()

        with self.assertRaises(ValueError):
            reg.register(_Provider("bad", "subtitle"))

        bad_tier = _Provider("bad2", stages.SCRIPT)
        bad_tier.capabilities = ProviderCapabilities(
            name="bad2", stage=stages.SCRIPT, quality_tier="luxury",
        )
        with self.assertRaises(ValueError):
            reg.register(bad_tier)

    def test_a_duplicate_name_in_the_same_stage_is_refused(self):
        reg = StageProviderRegistry()
        reg.register(_Provider("same", stages.SCRIPT))

        with self.assertRaises(ValueError):
            reg.register(_Provider("same", stages.SCRIPT))

    def test_the_same_name_in_a_different_stage_is_fine(self):
        reg = StageProviderRegistry()
        reg.register(_Provider("gemini", stages.SCRIPT))
        reg.register(_Provider("gemini", stages.IMAGE))

        self.assertEqual(len(reg), 2)

    def test_an_unavailable_provider_is_not_offered(self):
        """목록에 있는데 누르면 실패하는 상황을 만들지 않는다."""

        reg = StageProviderRegistry()
        reg.register(_Provider("no-key", stages.SCRIPT, available=False))

        self.assertEqual(reg.for_stage(stages.SCRIPT)[0].name, "no-key")
        self.assertEqual(reg.available(stages.SCRIPT), [])
        self.assertIsNone(reg.select(
            stages.SCRIPT,
            production_modes.policy_for(production_modes.AUTO_PREMIUM).quality_preference,
        ))


class TestCostIsNeverInvented(unittest.TestCase):

    def test_an_unknown_price_stays_unknown(self):
        provider = _Provider("no-price", stages.SCRIPT)

        estimate = provider.estimate_cost(None, source_modes.GENERATE)

        self.assertIsNone(estimate.amount)
        self.assertFalse(estimate.known)

    def test_a_breakdown_reports_what_it_does_not_know(self):
        reg = StageProviderRegistry()
        reg.register(_Provider("priced", stages.SCRIPT, amount=0.5))
        reg.register(_Provider("unpriced", stages.IMAGE))

        plan = ProductionPlan(mode=production_modes.AUTO_STANDARD)
        plan.select(StageSelection(stages.SCRIPT, source_modes.GENERATE, "priced"))
        plan.select(StageSelection(stages.IMAGE, source_modes.GENERATE, "unpriced"))

        breakdown = plan.estimate_cost(registry=reg)

        self.assertEqual(breakdown.known_total, 0.5)
        self.assertFalse(breakdown.complete)
        self.assertEqual(breakdown.unknown_stages, [stages.IMAGE])

    def test_an_unregistered_provider_is_unknown_not_free(self):
        plan = ProductionPlan(mode=production_modes.AUTO_STANDARD)
        plan.select(StageSelection(stages.SCRIPT, source_modes.GENERATE, "없는것"))

        breakdown = plan.estimate_cost(registry=StageProviderRegistry())

        self.assertFalse(breakdown.complete)
        self.assertEqual(breakdown.known_total, 0)

    def test_free_is_distinguishable_from_unknown(self):
        free = cost.free_estimate(stages.SCRIPT, "-", source_modes.MANUAL)

        self.assertTrue(free.known)
        self.assertTrue(free.free)


class TestThePlanIsCheckedBeforeAnythingIsMade(unittest.TestCase):

    def test_a_missing_stage_is_refused(self):
        plan = ProductionPlan(mode=production_modes.ASSISTED)
        plan.select(StageSelection(stages.SCRIPT, source_modes.MANUAL, payload="x"))

        with self.assertRaises(PlanError) as caught:
            plan.validate()

        self.assertIn("덜 찼습니다", str(caught.exception))

    def test_generation_without_a_provider_is_refused(self):
        plan = ProductionPlan(mode=production_modes.ASSISTED)
        for stage in stages.STAGES:
            plan.select(StageSelection(stage, source_modes.GENERATE, provider="p"))
        plan.selections[stages.IMAGE] = StageSelection(
            stages.IMAGE, source_modes.GENERATE, provider=None,
        )

        with self.assertRaises(PlanError):
            plan.validate()

    def test_manual_without_content_is_refused(self):
        plan = ProductionPlan(mode=production_modes.MANUAL)
        for stage in stages.STAGES:
            plan.select(StageSelection(stage, source_modes.MANUAL, payload="x"))
        plan.selections[stages.VOICE] = StageSelection(
            stages.VOICE, source_modes.MANUAL, payload=None,
        )

        with self.assertRaises(PlanError):
            plan.validate()

    def test_a_complete_plan_passes(self):
        plan = build_automatic_plan(production_modes.AUTO_PREMIUM, _full_registry())

        self.assertIs(plan.validate(), plan)

    def test_a_stage_with_no_available_provider_is_left_empty_not_guessed(self):
        reg = StageProviderRegistry()
        reg.register(_Provider("only-script", stages.SCRIPT))

        plan = build_automatic_plan(production_modes.AUTO_PREMIUM, reg)

        self.assertIn(stages.SCRIPT, plan.selections)
        self.assertEqual(
            sorted(plan.missing_stages()),
            sorted(s for s in stages.STAGES if s != stages.SCRIPT),
        )


class TestTheRegistryStartsEmpty(unittest.TestCase):
    """이번 스프린트는 Provider를 하나도 구현하지 않는다."""

    def test_no_provider_is_registered_yet(self):
        self.assertEqual(len(registry.default_registry()), 0)

    def test_the_current_engine_is_named(self):
        """지금 파이프라인이 하는 일이 어느 모드인지 분명히 해 둔다."""

        self.assertEqual(
            production_modes.CURRENT_ENGINE_MODE,
            production_modes.AUTO_STANDARD,
        )


class TestNothingWasWiredIn(unittest.TestCase):
    """Acceptance - 기존 Pipeline 영향 0, Upload/OAuth 영향 없음."""

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_the_pipeline_does_not_import_the_production_package(self):
        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("app.production", name)

    def test_only_the_studio_router_uses_it(self):
        import pathlib

        app_root = pathlib.Path(stages.__file__).parent.parent
        callers = []

        production_root = pathlib.Path(stages.__file__).parent

        for path in app_root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            # 패키지 안에서 서로를 부르는 것은 당연하다. Sprint103이
            # app/production/providers/ 하위 패키지를 더했으므로 바로
            # 위 디렉터리 이름만 보면 걸린다 - 경로로 판단한다.
            if production_root in path.parents:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                elif isinstance(node, ast.Import):
                    module = " ".join(a.name for a in node.names)
                if "app.production" in module:
                    callers.append(path.name)

        # Sprint102에는 "아무도 안 쓴다"였다. Sprint105가 제작 방식
        # 화면을 붙이며 라우터 하나가 쓰게 됐다 - 경계는 그 하나뿐이라는
        # 것으로 다시 세운다. Pipeline과 엔진은 여전히 모른다.
        self.assertEqual(sorted(set(callers)), ["studio.py"])

    def test_the_package_calls_no_api(self):
        """구조만 만든다 - Gemini/Imagen/ElevenLabs 연결 금지."""

        import pathlib

        base = pathlib.Path(stages.__file__).parent

        for path in base.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    with self.subTest(file=path.name, imported=name):
                        for banned in ("genai", "requests", "elevenlabs",
                                       "script_service", "image_service",
                                       "tts_provider", "openai", "anthropic"):
                            self.assertNotIn(banned, name)

    def test_production_endpoints_are_read_only(self):
        """Sprint102/103에는 "production 엔드포인트가 없어야 한다"였다.
        Sprint105가 제작 방식 화면을 붙이며 둘을 만들었으므로 그
        문장은 더 이상 사실이 아니다.

        지켜야 할 경계는 그대로다 - 셋 다 영상 생성을 시작하지
        않는다. project는 프로젝트만 만들고, 만드는 것은 여전히 기존
        생성 엔드포인트다(Sprint107)."""

        from app.main import app

        paths = [p for p in app.openapi()["paths"] if "production" in p.lower()]

        self.assertEqual(
            sorted(paths),
            ["/studio/api/production/import",
             "/studio/api/production/modes",
             "/studio/api/production/project"],
        )


if __name__ == "__main__":
    unittest.main()
