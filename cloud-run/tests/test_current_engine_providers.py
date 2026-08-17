"""
Sprint103 - 지금 엔진을 Provider로 감싼다 (Epic 54, Phase 2).

새 AI 연결도 새 API도 없다. 지금 파이프라인이 부르는 바로 그 함수를
Provider 계약 뒤에 두는 것이 전부다.

"결과가 같다"를 증명하는 방법으로 영상을 다시 만들지 않았다. 그것은
Gemini와 Imagen을 다시 부르는 일이고, 같은 설정으로 두 번 돌려도
결과가 다르다는 것을 이 저장소는 이미 안다(Sprint69: 같은 프롬프트로
overall_quality 40 vs 90). 대신 더 강한 것을 확인한다 - Provider가
파이프라인과 똑같은 함수를 똑같은 인자로 부른다는 사실. 같은 호출이면
결과가 같은지 물을 필요가 없다.
"""

import ast
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.production import production_modes, source_modes, stages
from app.production.production_plan import (
    PlanError,
    ProductionPlan,
    StageSelection,
    build_automatic_plan,
)
from app.production.providers import bootstrap
from app.production.providers.current_engine import (
    CURRENT,
    CURRENT_PROVIDER_CLASSES,
    CurrentImageProvider,
    CurrentMetadataProvider,
    CurrentScriptProvider,
    CurrentVoiceProvider,
)
from app.production.registry import StageProviderRegistry
from app.production.stage_provider import STANDARD, StageProviderError
from app.production.stage_request import StageRequest


def _registry():
    """항상 새 등록소를 쓴다 - 테스트끼리 상태를 넘기지 않는다."""

    reg = StageProviderRegistry()
    bootstrap.register_current_providers(reg)
    return reg


class TestEachProviderCallsTheRealEntryPoint(unittest.TestCase):
    """파이프라인이 실제로 부르는 그 함수를, 그 인자로 부른다.

    한 겹 아래(script_service.generate_script 같은 것)를 감쌌다면 그
    사이에 있는 Duration Gate와 Topic Fidelity(Sprint95), scene별 병렬
    처리, 오디오 병합이 빠져 결과가 달라진다."""

    def test_script_delegates_to_step01_with_the_same_arguments(self):
        from app.steps import step01_script

        with patch.object(step01_script, "run", return_value={"title": "t"}) as run:
            result = CurrentScriptProvider().generate(
                StageRequest(topic="혈관 건강", project_path="/p"),
            )

        run.assert_called_once_with("혈관 건강", "/p")
        self.assertEqual(result, {"title": "t"})

    def test_image_delegates_to_step02_collect_assets(self):
        from app.steps import step02_assets

        scenes = [{"scene": 1}]

        with patch.object(step02_assets, "collect_assets",
                          return_value=scenes) as collect:
            result = CurrentImageProvider().generate(
                StageRequest(scenes=scenes, project_path="/p", channel="foodbeat"),
            )

        collect.assert_called_once_with(scenes, "/p", "foodbeat")
        self.assertIs(result, scenes)

    def test_voice_delegates_to_step03_tts(self):
        from app.steps import step03_tts

        scenes = [{"scene": 1}]

        with patch.object(step03_tts, "run", return_value=None) as run:
            CurrentVoiceProvider().generate(
                StageRequest(scenes=scenes, project_path="/p"),
            )

        run.assert_called_once_with(scenes, "/p")

    def test_metadata_delegates_to_the_metadata_service(self):
        from app.services import metadata_service

        with patch.object(metadata_service, "generate_publish_package",
                          return_value={"title": "t"}) as generate:
            result = CurrentMetadataProvider().generate(
                StageRequest(project_path="/p"),
            )

        generate.assert_called_once_with("/p")
        self.assertEqual(result, {"title": "t"})

    def test_the_default_channel_matches_the_pipeline(self):
        from app.steps import step02_assets

        with patch.object(step02_assets, "collect_assets") as collect:
            CurrentImageProvider().generate(
                StageRequest(scenes=[{"scene": 1}], project_path="/p"),
            )

        self.assertEqual(collect.call_args[0][2], "wellbeing")


class TestMissingInputStopsBeforeTheEngine(unittest.TestCase):
    """만들 재료가 없으면 엔진을 부르지 않는다 - Gemini/Imagen 호출이
    낭비되지 않게."""

    def test_script_without_a_topic_refuses(self):
        from app.steps import step01_script

        with patch.object(step01_script, "run") as run:
            with self.assertRaises(ValueError):
                CurrentScriptProvider().generate(StageRequest(project_path="/p"))

        run.assert_not_called()

    def test_image_without_scenes_refuses(self):
        from app.steps import step02_assets

        with patch.object(step02_assets, "collect_assets") as collect:
            with self.assertRaises(ValueError):
                CurrentImageProvider().generate(StageRequest(project_path="/p"))

        collect.assert_not_called()

    def test_metadata_without_a_project_path_refuses(self):
        from app.services import metadata_service

        with patch.object(metadata_service, "generate_publish_package") as gen:
            with self.assertRaises(ValueError):
                CurrentMetadataProvider().generate(StageRequest())

        gen.assert_not_called()


class TestTheseAreWrappersNotNewCapabilities(unittest.TestCase):
    """지금 엔진에는 붙여넣기를 읽는 파서도, 업로드 파일을 받는
    경로도 없다. 없는 능력을 선언하지 않는다."""

    def test_only_generate_is_declared(self):
        for provider_class in CURRENT_PROVIDER_CLASSES:
            with self.subTest(provider=provider_class.__name__):
                provider = provider_class()
                self.assertEqual(
                    provider.capabilities.supported_source_modes,
                    (source_modes.GENERATE,),
                )

    def test_import_and_manual_raise_instead_of_returning_nothing(self):
        for provider_class in CURRENT_PROVIDER_CLASSES:
            provider = provider_class()
            with self.subTest(provider=provider_class.__name__):
                with self.assertRaises(StageProviderError):
                    provider.import_content("붙여넣은 텍스트")
                with self.assertRaises(StageProviderError):
                    provider.accept_manual("파일")

    def test_the_quality_tier_is_standard_not_premium(self):
        """지금 엔진 하나뿐이라 등급을 매길 상대가 없다. Premium이라고
        적어 두면 진짜 Premium이 들어올 때 판단 기준이 사라진다."""

        for provider_class in CURRENT_PROVIDER_CLASSES:
            with self.subTest(provider=provider_class.__name__):
                self.assertEqual(
                    provider_class().capabilities.quality_tier, STANDARD,
                )

    def test_they_all_share_one_name(self):
        names = {p().name for p in CURRENT_PROVIDER_CLASSES}

        self.assertEqual(names, {CURRENT})


class TestRegistrationIsCheapAndExplicit(unittest.TestCase):

    def test_registering_pulls_in_no_heavy_module(self):
        """script_service는 모듈을 읽는 것만으로 genai.Client를 만들고
        265개 모듈이 딸려 온다(실측). 등록이 그 비용을 내면 안 된다."""

        import subprocess

        code = (
            "import sys\n"
            "from app.production.providers import bootstrap\n"
            "from app.production.registry import StageProviderRegistry\n"
            "bootstrap.register_current_providers(StageProviderRegistry())\n"
            "print(len([m for m in sys.modules "
            "if m.startswith(('google.genai','vertexai','moviepy'))]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertEqual(result.stdout.strip(), "0")

    def test_the_engine_imports_are_all_inside_methods(self):
        from app.production.providers import current_engine

        tree = ast.parse(open(current_engine.__file__, encoding="utf-8").read())

        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                top_level.add(node.module or "")
            elif isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)

        for forbidden in ("step01", "step02", "step03", "script_service",
                          "metadata_service", "image_service"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in n for n in top_level), forbidden,
                )

    def test_registering_twice_is_safe(self):
        reg = StageProviderRegistry()

        first = bootstrap.register_current_providers(reg)
        second = bootstrap.register_current_providers(reg)

        # Sprint104가 chat_import를 더해 5개가 됐다. 숫자를 박아 두면
        # Provider가 늘 때마다 이 테스트가 깨진다 - 확인할 것은
        # "두 번 불러도 안전한가"이지 개수가 아니다.
        self.assertTrue(first)
        self.assertEqual(second, [])
        self.assertEqual(len(reg), len(first))

    def test_bootstrap_is_reported(self):
        reg = StageProviderRegistry()

        self.assertFalse(bootstrap.is_bootstrapped(reg))
        bootstrap.register_current_providers(reg)
        self.assertTrue(bootstrap.is_bootstrapped(reg))

    def test_nothing_is_registered_just_by_importing(self):
        """등록은 명시적으로 부를 때만 일어난다."""

        from app.production.registry import default_registry

        self.assertEqual(len(default_registry()), 0)

    def test_an_empty_registry_is_not_swapped_for_the_global_one(self):
        """실제로 났던 결함이다.

        Registry에 __len__을 정의해 둔 탓에 빈 등록소가 falsy가 되고,
        `registry = registry or default_registry()`가 조용히 전역
        등록소로 바꿔치기했다. 넘긴 것을 쓰지 않는 함수는 테스트도
        운영도 전부 거짓말이 된다."""

        from app.production.production_plan import build_automatic_plan
        from app.production.registry import default_registry

        empty = StageProviderRegistry()
        self.assertFalse(empty)          # 비어 있으면 falsy다 - 그 자체는 정상
        bootstrap.register_current_providers(default_registry())

        try:
            # 빈 등록소를 넘겼으니 아무것도 못 골라야 한다.
            plan = build_automatic_plan(production_modes.AUTO_STANDARD, empty)
            self.assertEqual(plan.selections, {})
            self.assertFalse(bootstrap.is_bootstrapped(empty))
        finally:
            default_registry()._providers = {
                stage: [] for stage in stages.STAGES
            }


class TestProductionModeSelection(unittest.TestCase):

    def test_every_auto_mode_selects_the_current_provider(self):
        """Provider가 늘어나기 전까지 셋 다 같은 것을 고른다."""

        reg = _registry()

        for mode in (production_modes.AUTO_PREMIUM,
                     production_modes.AUTO_STANDARD,
                     production_modes.AUTO_ECONOMY):
            plan = build_automatic_plan(mode, reg)
            for stage in (stages.SCRIPT, stages.IMAGE,
                          stages.VOICE, stages.METADATA):
                with self.subTest(mode=mode, stage=stage):
                    self.assertEqual(plan.selections[stage].provider, CURRENT)

    def test_music_is_left_empty_because_there_is_no_provider(self):
        """BGM은 렌더 중에 섞여 들어가고 별도 산출물이 없다. 감싸려면
        렌더 경로를 건드려야 하는데 이번 스프린트는 엔진을 고치지
        않는다."""

        plan = build_automatic_plan(production_modes.AUTO_STANDARD, _registry())

        self.assertEqual(plan.missing_stages(), [stages.MUSIC])

    def test_manual_mode_cannot_reach_generate(self):
        plan = ProductionPlan(mode=production_modes.MANUAL)

        with self.assertRaises(PlanError):
            plan.select(StageSelection(
                stages.SCRIPT, source_modes.GENERATE, provider=CURRENT,
            ))

    def test_the_current_provider_only_offers_generation(self):
        """Sprint103에는 "IMPORT를 맡을 Provider가 아직 없다"였다.
        Sprint104가 chat_import를 더했으므로 그 문장은 더 이상 사실이
        아니다.

        지켜야 할 경계는 그대로다 - current는 여전히 GENERATE만
        맡고, MANUAL은 아직 아무도 맡지 않는다."""

        reg = _registry()

        # Sprint124 - 자리는 여럿이 됐지만 실제로 쓸 수 있는 것은
        # 여전히 current 하나다. 나머지는 부르면 거절한다.
        usable = [
            p.name for p in reg.available(stages.SCRIPT, source_modes.GENERATE)
            if not getattr(p, "coming_soon", False)
        ]

        # Sprint133 - Gemini가 실제로 붙었다. 같은 모델을 부르지만
        # Writer·게이트·재시도를 거치지 않는 직접 호출 쪽이다.
        self.assertEqual(
            usable, [CURRENT, "gemini", "claude", "openai", "deepseek"])
        self.assertNotIn(
            CURRENT,
            [p.name for p in reg.available(stages.SCRIPT, source_modes.IMPORT)],
        )
        self.assertEqual(reg.available(stages.SCRIPT, source_modes.MANUAL), [])


class TestCost(unittest.TestCase):

    def test_metadata_is_known_to_be_free(self):
        """Sprint93의 메타데이터 엔진은 Gemini도 Imagen도 부르지
        않는다. 추측이 아니라 그 코드가 그렇다."""

        estimate = CurrentMetadataProvider().estimate_cost(
            StageRequest(), source_modes.GENERATE,
        )

        self.assertEqual(estimate.amount, 0.0)
        self.assertTrue(estimate.known)

    def test_the_others_report_unknown_rather_than_zero(self):
        """단가를 모르는데 0으로 채우면 "공짜"라는 거짓말이 된다."""

        for provider_class in (CurrentScriptProvider, CurrentImageProvider,
                               CurrentVoiceProvider):
            with self.subTest(provider=provider_class.__name__):
                estimate = provider_class().estimate_cost(
                    StageRequest(), source_modes.GENERATE,
                )
                self.assertIsNone(estimate.amount)

    def test_a_plan_shows_which_stages_it_cannot_price(self):
        reg = _registry()
        plan = build_automatic_plan(production_modes.AUTO_STANDARD, reg)

        breakdown = plan.estimate_cost(registry=reg)

        self.assertFalse(breakdown.complete)
        self.assertEqual(
            sorted(breakdown.unknown_stages),
            sorted([stages.SCRIPT, stages.IMAGE, stages.VOICE]),
        )


class TestTheEngineWasNotTouched(unittest.TestCase):
    """Acceptance - 기존 Engine 수정 금지, Pipeline 결과 동일."""

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
        """파이프라인은 지금까지 하던 대로 돈다 - Provider를 거치지
        않는다."""

        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("app.production", name)

    def test_the_engine_modules_do_not_know_about_providers(self):
        from app.services import metadata_service
        from app.steps import step01_script, step02_assets, step03_tts

        for module in (step01_script, step02_assets, step03_tts, metadata_service):
            for name in self._imports(module):
                with self.subTest(module=module.__name__, imported=name):
                    self.assertNotIn("app.production", name)

    def test_no_new_api_client_was_added(self):
        """새 AI 연결 금지 - Claude/GPT/Gemini/ElevenLabs 어느 것도
        새로 붙이지 않는다."""

        import pathlib

        from app.production.providers import current_engine

        base = pathlib.Path(current_engine.__file__).parent.parent

        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    with self.subTest(file=path.name, imported=name):
                        # Sprint125 - ElevenLabs는 app.production 안에
                        # 실제 Provider로 올라갔다. 다만 그 파일도 API
                        # 클라이언트를 직접 들이지는 않는다 - 이미 있는
                        # app/providers/elevenlabs_provider를 부를 뿐이다.
                        if "elevenlabs_voice" in name:
                            continue
                        for banned in ("openai", "anthropic", "genai",
                                       "elevenlabs", "requests"):
                            self.assertNotIn(banned, name)

    def test_production_endpoints_are_read_only(self):
        """Sprint102/103에는 "production 엔드포인트가 없어야 한다"였다.
        Sprint105가 제작 방식 화면을 붙이며 둘을 만들었으므로 그
        문장은 더 이상 사실이 아니다.

        지켜야 할 경계는 그대로다 - 전부 영상 생성을 시작하지
        않는다. project는 프로젝트만 만들고(Sprint107), images는
        사용자가 준 파일을 놓기만 하며(Sprint110/112), 만드는 것은 여전히
        기존 생성 엔드포인트다."""

        from app.main import app

        paths = [p for p in app.openapi()["paths"] if "production" in p.lower()]

        self.assertEqual(
            sorted(paths),
            [# Sprint218 - 만들기 갈래 목록. GET 하나이고
             # 아무것도 시작하지 않는다 - 이 가드가 지키는
             # 경계는 그대로다.
             "/studio/api/production/creation-modes",
             "/studio/api/production/images",
             "/studio/api/production/import",
             "/studio/api/production/modes",
             "/studio/api/production/plan",
             "/studio/api/production/project",
             "/studio/api/production/stages",
             "/studio/api/production/voice"],
        )


if __name__ == "__main__":
    unittest.main()
