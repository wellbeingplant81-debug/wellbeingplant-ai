"""
Sprint109 - 단계마다 어디서 가져올지 고른다 (Epic 54, Phase 8).

Provider를 추가하지 않는다. 고를 수 있는 범위와 그 선택이 무엇을
뜻하는지(비용/시간/API 사용)만 넓힌다. 실행은 붙이지 않는다 -
Plan까지만 만든다.

새로 생긴 것은 NONE 하나다. "그 단계를 건너뛴다"는 뜻이고, 이미지·
음성·배경음악에만 쓸 수 있다. 대본이 없으면 만들 것이 없으므로
대본에는 없다.

시간 예측은 지어내지 않는다. 이 저장소가 실제로 남긴 37편의
performance_metrics 중앙값을 쓴다.
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
    production_modes,
    source_modes,
    stage_timing,
    stages,
)
from app.production.production_plan import (
    PlanError,
    ProductionPlan,
    StageSelection,
)


class TestTheNewSkipMode(unittest.TestCase):

    def test_none_is_a_source_mode(self):
        self.assertIn(source_modes.NONE, source_modes.SOURCE_MODES)

    def test_skipping_calls_no_api(self):
        self.assertFalse(source_modes.calls_api(source_modes.NONE))

    def test_it_has_a_label_people_can_read(self):
        self.assertTrue(source_modes.LABELS[source_modes.NONE])

    def test_only_generate_still_costs_money(self):
        billable = set(source_modes.BILLABLE_SOURCE_MODES)

        self.assertEqual(billable, {source_modes.GENERATE})


class TestWhichStagesCanBeSkipped(unittest.TestCase):
    """대본이 없으면 만들 것이 없다."""

    def test_script_cannot_be_skipped(self):
        self.assertNotIn(
            source_modes.NONE, stages.allowed_source_modes(stages.SCRIPT),
        )

    def test_image_voice_and_music_can_be_skipped(self):
        for stage in (stages.IMAGE, stages.VOICE, stages.MUSIC):
            with self.subTest(stage=stage):
                self.assertIn(
                    source_modes.NONE, stages.allowed_source_modes(stage),
                )

    def test_every_stage_offers_generate(self):
        for stage in stages.STAGES:
            with self.subTest(stage=stage):
                self.assertIn(
                    source_modes.GENERATE, stages.allowed_source_modes(stage),
                )

    def test_an_unknown_stage_is_refused(self):
        with self.assertRaises(ValueError):
            stages.allowed_source_modes("subtitle")


class TestThePlanAcceptsSkipping(unittest.TestCase):

    def _plan(self):
        return ProductionPlan(mode=production_modes.ASSISTED)

    def test_a_skipped_stage_needs_neither_provider_nor_payload(self):
        plan = self._plan()

        for stage in stages.STAGES:
            mode = (
                source_modes.NONE
                if source_modes.NONE in stages.allowed_source_modes(stage)
                else source_modes.MANUAL
            )
            plan.select(StageSelection(
                stage, mode, payload=None if mode == source_modes.NONE else "준 것",
            ))

        self.assertIs(plan.validate(), plan)

    def test_skipping_the_script_is_refused(self):
        plan = self._plan()

        with self.assertRaises(PlanError) as caught:
            plan.select(StageSelection(stages.SCRIPT, source_modes.NONE))

        self.assertIn("대본", str(caught.exception))

    def test_a_skipped_stage_reports_no_api(self):
        plan = self._plan()
        plan.select(StageSelection(
            stages.SCRIPT, source_modes.IMPORT, payload="붙여넣음",
        ))
        for stage in (stages.IMAGE, stages.VOICE, stages.MUSIC,
                      stages.METADATA):
            plan.select(StageSelection(stage, source_modes.NONE)
                        if stage != stages.METADATA
                        else StageSelection(stage, source_modes.GENERATE,
                                            provider="current"))

        self.assertEqual(plan.api_stages, [stages.METADATA])

    def test_skipping_costs_nothing(self):
        plan = self._plan()
        plan.select(StageSelection(stages.IMAGE, source_modes.NONE))

        estimate = plan.estimate_cost().estimates[0]

        self.assertEqual(estimate.amount, 0.0)


class TestTimeComesFromRealMeasurements(unittest.TestCase):
    """지어내지 않는다 - 이 저장소가 남긴 37편의 중앙값이다."""

    def test_the_sample_is_recorded(self):
        self.assertGreater(stage_timing.SAMPLE_SIZE, 0)
        self.assertTrue(stage_timing.MEASURED_AT)

    def test_every_selectable_stage_has_a_measured_second(self):
        for stage in stages.STAGES:
            with self.subTest(stage=stage):
                self.assertIn(stage, stage_timing.STAGE_SECONDS)

    def test_the_fixed_part_is_the_steps_the_user_cannot_choose(self):
        """자막·렌더·썸네일·품질은 고를 수 있는 것이 아니다 - 항상
        돈다."""

        self.assertGreater(stage_timing.FIXED_SECONDS, 0)

    def test_skipping_a_stage_shortens_the_estimate(self):
        plan = ProductionPlan(mode=production_modes.ASSISTED)
        plan.select(StageSelection(stages.SCRIPT, source_modes.IMPORT,
                                   payload="x"))
        plan.select(StageSelection(stages.IMAGE, source_modes.GENERATE,
                                   provider="current"))
        with_image = plan.estimate_seconds()

        plan.select(StageSelection(stages.IMAGE, source_modes.NONE))

        self.assertLess(plan.estimate_seconds(), with_image)

    def test_importing_costs_no_time_for_that_stage(self):
        """붙여넣은 것은 만드는 시간이 들지 않는다."""

        generated = ProductionPlan(mode=production_modes.ASSISTED)
        generated.select(StageSelection(stages.SCRIPT, source_modes.GENERATE,
                                        provider="current"))

        imported = ProductionPlan(mode=production_modes.ASSISTED)
        imported.select(StageSelection(stages.SCRIPT, source_modes.IMPORT,
                                       payload="x"))

        self.assertLess(imported.estimate_seconds(),
                        generated.estimate_seconds())

    def test_the_fixed_part_is_always_included(self):
        plan = ProductionPlan(mode=production_modes.ASSISTED)
        plan.select(StageSelection(stages.SCRIPT, source_modes.IMPORT,
                                   payload="x"))

        self.assertGreaterEqual(plan.estimate_seconds(),
                                stage_timing.FIXED_SECONDS)


class TestTheEndpoint(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_it_lists_what_each_stage_allows(self):
        data = self.client.get("/studio/api/production/stages").json()

        by_stage = {row["stage"]: row for row in data["stages"]}

        self.assertIn("none", by_stage["image"]["source_modes"])
        self.assertNotIn("none", by_stage["script"]["source_modes"])

    def test_it_builds_a_plan_with_cost_and_time(self):
        response = self.client.post("/studio/api/production/plan", json={
            "selections": {
                "script": "import", "image": "generate",
                "voice": "none", "music": "none", "metadata": "generate",
            },
        })

        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("cost", body)
        self.assertIn("estimated_seconds", body)
        self.assertEqual(body["api_stages"], ["image", "metadata"])

    def test_metadata_cannot_be_skipped(self):
        """비우면 제목 없는 영상이 업로드된다 - 업로드가 읽는
        자리다(Sprint93)."""

        response = self.client.post("/studio/api/production/plan", json={
            "selections": {"metadata": "none"},
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("메타데이터", response.json()["detail"])

    def test_giving_everything_yourself_uses_no_api_at_all(self):
        body = self.client.post("/studio/api/production/plan", json={
            "selections": {
                "script": "manual", "image": "none",
                "voice": "none", "music": "none", "metadata": "manual",
            },
        }).json()

        self.assertFalse(body["calls_api"])
        self.assertEqual(body["api_stages"], [])

    def test_an_invalid_selection_is_refused_with_a_reason(self):
        response = self.client.post("/studio/api/production/plan", json={
            "selections": {"script": "none"},
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("대본", response.json()["detail"])


class TestNothingWasExecuted(unittest.TestCase):
    """Plan까지만 만든다. Pipeline/Provider/step01~07 수정 금지."""

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

    def test_the_timing_table_calls_nothing(self):
        self.assertEqual(self._imports(stage_timing), set())

    def test_no_provider_was_added(self):
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        self.assertEqual(
            sorted(p.name for p in registry.for_stage(stages.SCRIPT)),
            ["chat_import", "current"],
        )
        self.assertEqual(registry.for_stage(stages.MUSIC), [])


if __name__ == "__main__":
    unittest.main()
