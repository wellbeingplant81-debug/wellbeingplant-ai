"""
Sprint119 - Studio UX 5.0 (Epic 54, Phase 18).

Provider 중심에서 결과 중심으로 옮긴다. 사용자가 먼저 정하는 것은
"어떤 결과를 원하는가"이고, 어떤 모델이 도는지는 그다음이다.

금액에 대해
-----------
"500원 이하" 같은 말은 측정된 값이 아니다. 지금 어느 Provider도 단가를
신고하지 않아서 known_total은 늘 0이고 unknown_stages가 남는다. 그래서
카드의 금액은 사용자가 고르는 *목표*로만 쓰고, 실제로 아는 것(무료 /
계산 불가)은 요약이 따로 말한다. 둘을 섞으면 화면이 모르는 것을 아는
척하게 된다.

예상 결과에 대해
----------------
새 알고리즘을 만들지 않는다. 쓰는 것은 넷뿐이고 전부 이미 있는 값이다.

    품질      Provider가 신고한 quality_tier
    제작속도  계획의 estimated_seconds를 실측 범위 안에 놓은 위치
              (303.1초 = 전부 직접, 353.0초 = 전부 AI · 실측 37편)
    비용      돈이 나가는 단계 수 (engine.calls_api) - 금액이 아니다
    자동화    고른 것에서 센 비율

없는 값은 만들지 않는다 - 그래서 "비용"은 별로 그리되 그 근거가
금액이 아니라는 것을 화면이 함께 적는다.
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


class TestTheResultPresetsWereReplaced(unittest.TestCase):
    """Sprint120 - 예산으로 묻던 것을 가진 자료로 바꿨다.

    금액은 우리가 계산할 수 없는 값이라 카드가 "목표"라고 적어 두는
    수밖에 없었다. 이제 사용자가 답을 아는 것만 묻는다. 새 질문은
    test_studio_ux6가 본다."""

    def test_the_situations_took_their_place(self):
        page = _page()

        self.assertNotIn("const PRESETS", page)
        self.assertIn("const HAVE_ITEMS", page)

    def test_it_still_only_sets_defaults(self):
        page = _page()
        block = _block(page, "async function recommend")

        self.assertIn("uiPick", block)
        self.assertNotIn("disabled", block)


class TestTheMoneyIsNotInvented(unittest.TestCase):
    """지금 단가를 아는 Provider가 하나도 없다."""

    def test_no_provider_reports_a_unit_price(self):
        plan = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate", "image": "generate",
                                 "voice": "generate", "metadata": "generate",
                                 "music": "generate"}},
        ).json()

        self.assertEqual(plan["cost"]["known_total"], 0.0)
        self.assertFalse(plan["cost"]["complete"])

    def test_the_screen_no_longer_asks_about_money(self):
        """Sprint120 - 카드가 금액을 말하지 않게 되면서 이 문제가
        아예 사라졌다. 우리가 계산할 수 없는 것을 묻지 않는다."""

        page = _page()
        block = _block(page, "function haveCard")

        self.assertNotIn("원", block)
        self.assertNotIn("amount", block)

    def test_the_summary_still_shows_what_is_actually_known(self):
        page = _page()
        block = _block(page, "function costWording")

        # Sprint168 - 문구만 바뀌었다. 지킬 것은 그대로다.
        self.assertIn("NO_COST", block)
        self.assertIn('const NO_COST = "API 비용 없음"', page)

        for wording in ("계산 불가",):
            with self.subTest(wording=wording):
                self.assertIn(wording, block)


class TestTheStageListIsSimplified(unittest.TestCase):

    def test_only_three_stages_are_shown_by_default(self):
        page = _page()
        block = _block(page, "const BASIC_STAGES", "\n")

        for stage in ("script", "image", "voice"):
            with self.subTest(stage=stage):
                self.assertIn(stage, block)

        self.assertNotIn("metadata", block)

    def test_metadata_moved_into_advanced(self):
        page = _page()

        self.assertIn("고급 설정", page)

        block = _block(page, "const ADVANCED_STAGES", "\n")
        self.assertIn("metadata", block)

    def test_advanced_is_closed_at_first(self):
        page = _page()

        self.assertIn('id="advanced"', page)
        block = page[page.index('id="advanced"'):][:220]

        self.assertIn("display:none", block)

    def test_metadata_still_reaches_the_plan(self):
        """화면에서 접었다고 계획에서 빠지면 안 된다."""

        page = _page()

        self.assertIn("ADVANCED_STAGES", _block(page, "async function loadStages"))

        plan = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate", "image": "generate",
                                 "voice": "generate", "metadata": "generate",
                                 "music": "generate"}},
        ).json()

        self.assertIn("metadata", plan["stages"])


class TestTheProviderNameIsSecondary(unittest.TestCase):

    def test_the_card_face_is_plain_language(self):
        page = _page()
        block = _block(page, "function providerCard")

        self.assertIn("plainLabel", block)

    def test_the_plain_label_never_names_a_model(self):
        page = _page()
        block = _block(page, "function plainLabel")

        for model in ("Gemini", "Imagen", "Chirp3"):
            with self.subTest(model=model):
                self.assertNotIn(model, block)

    def test_the_real_provider_shows_once_it_is_chosen(self):
        page = _page()
        block = _block(page, "function providerCard")

        self.assertIn("engine.name", block)

    def test_the_model_id_is_available_too(self):
        served = {r["stage"]: r["engine"]
                  for r in client.get(
                      "/studio/api/production/stages").json()["stages"]}

        self.assertEqual(served["script"]["model"], "gemini-2.5-pro")
        self.assertIn("engine.model", _page())


class TestTheExpectedResultCard(unittest.TestCase):

    def test_the_four_ratings_exist(self):
        page = _page()
        block = _block(page, "function expectedResult")

        # Sprint137 - "제작속도"는 등급으로 읽힌다. 잰 것은 시간이므로
        # 시간이라고 적는다.
        for label in ("품질", "제작시간", "비용", "자동화"):
            with self.subTest(label=label):
                self.assertIn(label, block)

    def test_time_shows_the_measured_number_not_a_rating(self):
        """
        Sprint137 - 초는 사실이고 별은 의견이다. 1~5로 환산하는 순간
        "빠르다 느리다"라는 판정이 되므로 잰 숫자를 그대로 적는다.
        """

        page = _page()
        block = _block(page, "function expectedResult")

        self.assertIn("estimated_seconds", block)
        self.assertIn("sample_size", block)
        self.assertIn("MEASURED", block)

    def test_cost_says_it_does_not_know_the_price(self):
        """단가를 아는 Provider가 하나도 없다."""

        page = _page()
        block = _block(page, "function expectedResult")

        self.assertIn("payingStages", block)
        self.assertIn("단가", block)

    def test_quality_says_it_was_never_measured(self):
        page = _page()
        block = _block(page, "function expectedResult")
        quality = block[block.index("품질"):block.index("제작시간")]

        self.assertIn("UNMEASURED", quality)


class TestTheHeaderLine(unittest.TestCase):

    def test_it_is_a_single_plain_line(self):
        page = _page()
        block = _block(page, "function renderCurrentProviders")

        self.assertIn("plainLabel", block)

    def test_it_is_redrawn_on_every_change(self):
        page = _page()

        for fn in ("async function pickStage", "async function recommend"):
            with self.subTest(fn=fn):
                self.assertIn("renderCurrentProviders", _block(page, fn))


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

    def test_the_providers_are_untouched(self):
        from app.production.providers import (
            chat_import, current_engine, image_import, voice_import,
        )

        for module in (chat_import, current_engine, image_import,
                       voice_import):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("원", source.split('"""')[-1])
                self.assertNotIn("studio", source)

    def test_the_plan_contract_is_unchanged(self):
        response = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate"}},
        )

        self.assertEqual(response.status_code, 200)
        for invented in ("preset", "budget", "result"):
            with self.subTest(key=invented):
                self.assertNotIn(invented, response.json())

    def test_the_generate_button_still_posts_the_same_job(self):
        page = _page()

        self.assertIn('id="go"', page)
        self.assertIn("/studio/api/jobs", page)


if __name__ == "__main__":
    unittest.main()
