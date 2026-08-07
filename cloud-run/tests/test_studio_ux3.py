"""
Sprint117 - Studio UX 3.0 (Epic 54, Phase 16).

"AI 생성"을 걷어낸다. 무슨 AI인지 말하지 않는 이름이었다.

Sprint116이 등급(Premium/Standard/Economy)을 없앴는데도 그 자리를
"AI 생성"이 물려받아서, 사용자는 여전히 무엇이 도는지 몰랐다. 이번에는
실제로 도는 것의 이름을 적는다.

    대본      gemini-2.5-pro
    이미지    imagen-4.0-generate-001
    음성      ko-KR-Chirp3-HD-Aoede
    메타데이터 규칙 기반 (API 없음)
    배경음악  로컬 mp3 (API 없음)

이 문자열들은 서비스 함수 안에 인라인으로 박혀 있어 import할 상수가
없다. 그래서 화면 쪽에 적고, 그것이 실제 코드와 어긋나지 않는지는
여기서 잠근다 - 모델을 바꾸면 이 테스트가 먼저 깨진다.

품질 별점은 지어내지 않는다. Provider가 신고한 quality_tier를 별로
그리는 것뿐이고, 등급 이름도 함께 보여 준다.
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


def _stages():
    return client.get("/studio/api/production/stages").json()["stages"]


def _by_stage():
    return {row["stage"]: row for row in _stages()}


class TestTheEngineIsNamed(unittest.TestCase):
    """무슨 AI인지 화면이 말한다."""

    def test_every_stage_reports_what_actually_runs(self):
        for stage, row in _by_stage().items():
            with self.subTest(stage=stage):
                self.assertIn("engine", row)
                self.assertTrue(row["engine"]["name"])

    def test_the_named_models_exist_in_the_code(self):
        """적어 둔 모델이 실제로 도는 그것인지 잠근다."""

        from app.providers import google_tts_provider
        from app.services import image_service, script_service

        where = {
            "script": script_service,
            "image": image_service,
            "voice": google_tts_provider,
        }

        for stage, module in where.items():
            model = _by_stage()[stage]["engine"]["model"]
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(stage=stage, model=model):
                self.assertTrue(model)
                self.assertIn(model, source)

    def test_the_free_stages_call_no_api(self):
        """메타데이터는 규칙 기반이고 BGM은 로컬 파일이다."""

        rows = _by_stage()

        for stage in ("metadata", "music"):
            with self.subTest(stage=stage):
                self.assertFalse(rows[stage]["engine"]["calls_api"])
                self.assertIsNone(rows[stage]["engine"]["model"])

    def test_metadata_really_imports_no_ai(self):
        from app.services import metadata_service

        tree = ast.parse(open(metadata_service.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)

        for forbidden in ("genai", "vertexai", "openai"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(any(forbidden in n for n in names))

    def test_the_paying_stages_are_the_three(self):
        rows = _by_stage()

        paying = sorted(s for s, r in rows.items() if r["engine"]["calls_api"])

        self.assertEqual(paying, ["image", "script", "voice"])


class TestTheAbstractWordingIsGone(unittest.TestCase):

    def test_the_phrase_ai_generate_is_not_a_label(self):
        """"AI 생성"이라는 이름을 더 이상 쓰지 않는다."""

        page = _page()
        labels = re.findall(r'label:\s*"([^"]+)"', page)

        self.assertTrue(labels)
        for label in labels:
            with self.subTest(label=label):
                self.assertNotEqual(label, "AI 생성")

    def test_the_coming_soon_wording_replaced_the_planned_one(self):
        page = _page()

        self.assertIn("Coming Soon", page)
        self.assertNotIn("(예정)", page)
        self.assertIn("향후 지원 예정", page)

    def test_elevenlabs_cannot_be_clicked(self):
        page = _page()

        card = page[page.index("ElevenLabs") - 200:page.index("ElevenLabs") + 200]

        self.assertIn("soon", card)


class TestTheProviderCard(unittest.TestCase):
    """카드는 다섯만 말한다 - 이름 · 현재 여부 · 품질 · 비용 · 지원 여부."""

    def test_the_card_renders_those_five(self):
        page = _page()

        block = page[page.index("function providerCard"):]
        block = block[:block.index("\nfunction ")]

        # Sprint119 - 이름은 평이한 말이 되고(plainLabel) 현재 엔진은
        # 고른 뒤 한 줄로 붙는다. 다섯 가지는 그대로다.
        for piece in ("plainLabel", "현재 엔진", "starText", "cost", "soon"):
            with self.subTest(piece=piece):
                self.assertIn(piece, block)

    def test_the_card_carries_no_prose(self):
        """설명문 최소화 - 카드에 description을 싣지 않는다."""

        page = _page()

        block = page[page.index("function providerCard"):]
        block = block[:block.index("\nfunction ")]

        self.assertNotIn("description", block)

    def test_the_current_engine_is_marked(self):
        self.assertIn("Current", _page())

    def test_the_stars_are_the_reported_tier_not_a_guess(self):
        from app.production import stage_provider

        page = _page()

        block = page[page.index("const STARS"):]
        block = block[:block.index("}") + 1]

        for tier in stage_provider.QUALITY_TIERS:
            with self.subTest(tier=tier):
                self.assertIn(tier, block)

    def test_the_tier_name_is_shown_next_to_the_stars(self):
        """별만 있으면 무엇을 근거로 넷인지 알 수 없다."""

        self.assertIn("quality", _page())

    def test_a_free_option_says_free(self):
        """Sprint118이 "Unknown"을 사람의 말로 바꿨다.

        이 단언은 Sprint118 이후에도 통과했는데, 그 단어를 왜 뺐는지
        적어 둔 주석에 걸려 있었을 뿐이다. Sprint119에서 그 주석이
        사라지며 드러났다 - 화면에 보이는 글로 다시 세운다."""

        page = _page()

        self.assertIn("무료", page)
        self.assertIn("단가 미상", page)


class TestTheSummaryIsCards(unittest.TestCase):

    def test_the_four_cards_are_there(self):
        """Sprint119 - 품질과 자동화는 예상 결과 카드로 옮겼다.
        요약 전체(예상 결과 + 카드)에서 본다."""

        page = _page()

        block = page[page.index("function expectedResult"):]
        block = block[:block.index("\nasync function ")]

        for label in ("예상 비용", "예상 시간", "품질", "API"):
            with self.subTest(label=label):
                self.assertIn(label, block)

    def test_the_summary_is_no_longer_a_definition_list(self):
        page = _page()

        block = page[page.index("function summaryCards"):]
        block = block[:block.index("\nasync function ")]

        self.assertNotIn("<dl>", block)
        self.assertIn("card", block)

    def test_the_api_count_excludes_the_free_stages(self):
        """계획의 api_stages는 generate면 전부 센다 - 메타데이터는
        규칙 기반이고 BGM은 로컬 파일인데도 들어간다. 카드는 실제로
        돈이 나가는 것만 센다."""

        plan = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate", "image": "generate",
                                 "voice": "generate", "metadata": "generate",
                                 "music": "generate"}},
        ).json()

        self.assertEqual(len(plan["api_stages"]), 5)

        page = _page()
        self.assertIn("engine.calls_api", page)


class TestTheCurrentProviderCard(unittest.TestCase):
    """우측 상단에 항상 표시."""

    def test_it_exists(self):
        page = _page()

        self.assertIn('id="currentProviders"', page)

    def test_it_sits_in_the_header(self):
        page = _page()

        header = page[page.index("<header>"):page.index("</header>")]

        self.assertIn("currentProviders", header)

    def test_it_names_the_four_stages(self):
        page = _page()

        block = page[page.index("function renderCurrentProviders"):]
        block = block[:block.index("\nfunction ")]

        # Sprint118 - 엔진 이름이 아니라 "지금 고른 방식"을 적는다.
        # Sprint119 - 그 방식을 평이한 말로 적는다(plainLabel).
        self.assertIn("plainLabel", block)
        self.assertIn("uiPick", block)


class TestNothingBehindTheScreenMoved(unittest.TestCase):
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

    def test_the_provider_implementations_are_untouched(self):
        from app.production.providers import (
            chat_import, current_engine, image_import, voice_import,
        )

        for module in (chat_import, current_engine, image_import,
                       voice_import):
            source = open(module.__file__, encoding="utf-8").read()
            with self.subTest(module=module.__name__):
                self.assertNotIn("studio", source)
                self.assertNotIn("stars", source)

    def test_the_generate_button_still_posts_the_same_job(self):
        page = _page()

        self.assertIn('id="go"', page)
        self.assertIn("/studio/api/jobs", page)


if __name__ == "__main__":
    unittest.main()
