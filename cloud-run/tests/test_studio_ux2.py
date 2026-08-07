"""
Sprint116 - Studio UX 2.0 (Epic 54, Phase 15).

"제작 방식"을 먼저 고르게 하던 화면을 걷어내고, 단계마다 무엇으로
만들지 직접 고르는 화면으로 바꾼다.

Premium / Standard / Economy가 사라지는 이유는 그것이 사용자에게
아무것도 말해 주지 않기 때문이다. 어떤 AI가 쓰이는지도, 비용이 어디서
나는지도 등급 이름에는 없다. 단계마다 무엇을 고를지 보여 주면 그
셋이 저절로 답해진다.

ProductionMode는 없어지지 않는다 - 계획을 만들 때 내부에서 계속
쓰이고 엔드포인트도 그대로다. 화면에서만 사라진다.

이 파일은 화면과 그것을 먹여 주는 계약만 본다. 파이프라인도 엔진도
Resolver도 Provider도 건드리지 않았다는 것을 함께 묶어 둔다.
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


class TestThePremiumUiIsGone(unittest.TestCase):

    def test_the_mode_panel_is_removed(self):
        page = _page()

        self.assertNotIn('id="modes"', page)
        self.assertNotIn("제작 방식", page)

    def test_the_tier_names_are_not_offered_as_choices(self):
        page = _page()

        for name in ("Auto Premium", "Auto Standard", "Auto Economy",
                     "auto_premium", "auto_standard", "auto_economy"):
            with self.subTest(name=name):
                self.assertNotIn(name, page)

    def test_the_mode_endpoint_still_exists(self):
        """ProductionMode는 내부에서 계속 쓰인다 - 화면에서만 뺀다."""

        response = client.get("/studio/api/production/modes")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["modes"])

    def test_the_plan_is_still_built_from_a_production_mode(self):
        from app.production import production_modes

        response = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate"}},
        )

        self.assertEqual(response.json()["mode"], production_modes.ASSISTED)


class TestTheNewShape(unittest.TestCase):

    def test_the_heading_is_the_new_one(self):
        self.assertIn("새 영상 만들기", _page())

    def test_the_maker_sits_above_the_three_columns(self):
        """왼쪽 280px 칸에 갇혀 있던 것을 폭 전체로 꺼낸다."""

        page = _page()

        self.assertLess(page.index('class="maker"'), page.index('class="layout"'))

    def test_the_summary_is_pinned(self):
        page = _page()

        block = page[page.index(".maker-summary"):][:200]
        self.assertIn("sticky", block)

    def test_the_generate_button_lives_in_the_summary(self):
        """항상 보이려면 고정된 쪽에 있어야 한다."""

        page = _page()

        summary = page[page.index('id="makerSummary"'):]
        summary = summary[:summary.index("</aside>")]

        self.assertIn('id="go"', summary)

    def test_the_left_column_is_no_longer_a_tower(self):
        """제작 방식 · 단계별 선택 · Project · 최근 프로젝트 넷이
        세로로 쌓여 있던 자리다."""

        page = _page()

        first_stack = page[page.index('<div class="stack">'):]
        first_stack = first_stack[:first_stack.index("<!-- 중:")]

        self.assertEqual(first_stack.count('class="panel"'), 1)


class TestTheStageChoices(unittest.TestCase):

    def test_the_four_sections_are_offered(self):
        """구역 이름은 서버가 소유한다(stages.LABELS) - 화면이 다시
        적으면 한쪽만 바뀌는 날이 온다. 그래서 화면에서 확인할 것은
        어떤 단계를 그리는가이고, 이름은 계약에서 확인한다."""

        from app.production import stages

        page = _page()
        offered = re.search(r"const STAGE_UI = \{(.*?)\n\};", page, re.S).group(1)
        drawn = re.findall(r"^  (\w+):", offered, re.M)

        self.assertEqual(drawn, ["script", "image", "voice", "metadata"])

        served = {r["stage"]: r["label"]
                  for r in client.get("/studio/api/production/stages").json()["stages"]}

        for stage in drawn:
            with self.subTest(stage=stage):
                self.assertEqual(served[stage], stages.LABELS[stage])

        self.assertIn("spec.label", page)

    def test_the_script_offers_six_ways(self):
        """Sprint117 - 라벨이 바뀌었다. AI 생성은 실제 모델 이름을
        서버에서 받아 오고(engine.name), 붙여넣기는 도구 이름만 남았다.
        가짓수는 여섯 그대로다."""

        page = _page()
        block = page[page.index("  script: ["):]
        block = block[:block.index("  ],")]

        self.assertEqual(block.count("{key:"), 6)

        for tool in ("ChatGPT", "Claude", "Gemini", "DeepSeek", "직접 작성"):
            with self.subTest(tool=tool):
                self.assertIn(tool, block)

        self.assertIn("engine:true", block)

    def test_the_image_offers_three_ways(self):
        page = _page()

        for label in ("직접 업로드", "사용 안 함"):
            with self.subTest(label=label):
                self.assertIn(label, page)

    def test_the_voice_names_the_engine_that_actually_runs(self):
        """"AI 생성"으로는 어떤 AI인지 알 수 없다는 것이 문제였다.

        Sprint117 - 이름을 화면에 적어 두지 않는다. 실제로 도는 것을
        서버가 알려 주고 화면은 그것을 그린다."""

        served = {r["stage"]: r["engine"]["name"]
                  for r in client.get(
                      "/studio/api/production/stages").json()["stages"]}

        self.assertIn("Google TTS", served["voice"])
        self.assertIn("engine.name", _page())

    def test_elevenlabs_is_shown_but_not_selectable(self):
        """Sprint124 - 고르는 목록에서 빼고 Provider 목록으로 옮겼다.
        같은 사실을 두 곳에 적지 않는다."""

        served = client.get("/studio/api/production/stages").json()["stages"]
        voice = [r for r in served if r["stage"] == "voice"][0]
        eleven = [p for p in voice["provider_list"]
                  if p["display_name"] == "ElevenLabs"]

        self.assertEqual(len(eleven), 1)
        self.assertTrue(eleven[0]["coming_soon"])
        self.assertIn("향후 지원 예정", _page())

    def test_every_offered_mode_is_a_real_source_mode(self):
        """화면이 서버가 모르는 값을 보내면 400이 난다."""

        from app.production import source_modes

        page = _page()
        offered = set(re.findall(r'mode:\s*"([a-z]+)"', page))

        self.assertTrue(offered)
        for mode in offered:
            with self.subTest(mode=mode):
                self.assertIn(mode, source_modes.SOURCE_MODES)

    def test_the_music_stage_is_not_a_choice_but_is_disclosed(self):
        """BGM은 렌더 중에 섞인다 - 고를 것이 없지만 숨기지도 않는다.

        문구는 stages.NOTES가 소유하므로 화면은 그것을 읽어 요약에
        싣는다. 여기서 확인할 것은 그 배선과, 계획에는 여전히 music이
        들어간다는 사실이다."""

        from app.production import stages

        page = _page()

        self.assertIn('HIDDEN_STAGES = ["music"]', page)
        self.assertIn('s.stage === "music"', page)
        self.assertIn("배경음악", page)
        self.assertTrue(stages.NOTES[stages.MUSIC])

    def test_music_still_reaches_the_plan(self):
        """화면에서 안 보인다고 계획에서 빠지면 안 된다 - 엔진은
        여전히 BGM을 섞는다."""

        page = _page()

        self.assertIn('stagePick[stage] = "generate"', page)

        plan = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate", "image": "generate",
                                 "voice": "generate", "metadata": "generate",
                                 "music": "generate"}},
        ).json()

        self.assertIn("music", plan["stages"])


class TestTheSummary(unittest.TestCase):

    def test_it_shows_the_five_things(self):
        page = _page()

        # Sprint117 - 텍스트 목록이 카드가 되면서 "API 호출"은 "API",
        # "Provider"는 헤더의 현재 Provider 카드로 옮겼다.
        for label in ("예상 비용", "예상 시간", "API", "품질",
                      "currentProviders"):
            with self.subTest(label=label):
                self.assertIn(label, page)

    def test_the_cost_wording_is_kept(self):
        """Sprint105가 정한 세 경우의 문구를 그대로 쓴다."""

        page = _page()

        # Sprint118 - 라벨과 값이 카드에서 나뉘었다. 세 경우는 그대로다.
        self.assertIn("예상 비용", page)
        self.assertIn("계산 불가", page)
        self.assertIn("무료", page)

    def test_the_quality_comes_from_the_providers_not_from_a_guess(self):
        data = client.get("/studio/api/production/stages").json()

        script = [r for r in data["stages"] if r["stage"] == "script"][0]

        self.assertEqual(script["provider_quality"]["current"], "standard")

    def test_every_named_provider_carries_a_quality(self):
        from app.production import stage_provider

        data = client.get("/studio/api/production/stages").json()

        for row in data["stages"]:
            named = {n for names in row["providers"].values() for n in names}
            for name in named:
                with self.subTest(stage=row["stage"], provider=name):
                    self.assertIn(
                        row["provider_quality"][name],
                        stage_provider.QUALITY_TIERS,
                    )


class TestTheEngineWasNotTouched(unittest.TestCase):
    """UI/Plan만 바꾼다."""

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_the_pipeline_does_not_know_the_production_package(self):
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
        """화면이 바뀐다고 Provider가 바뀔 이유가 없다."""

        from app.production.providers import (
            chat_import, image_import, voice_import,
        )

        for module in (chat_import, image_import, voice_import):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("studio", source)


if __name__ == "__main__":
    unittest.main()
