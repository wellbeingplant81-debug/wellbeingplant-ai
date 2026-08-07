"""
Sprint118 - Studio UX 4.0 (Epic 54, Phase 17).

Sprint117이 Provider 이름을 보여 줬다. 그런데 사용자가 정해야 하는 것은
이름이 아니라 셋이다.

    얼마까지 쓸 것인가
    어느 품질을 원하는가
    무엇을 직접 만들 것인가

그래서 위에 제작 전략을 두고, 그것이 단계별 기본값을 정하게 한다.
정하기만 하고 가두지 않는다 - 고른 뒤에도 단계마다 다시 바꿀 수 있다.

전략이 무엇을 바꿀 수 있는지는 지금 등록소가 정한다. 단계마다 Provider가
하나뿐이라(전부 "current") 전략이 더 싼 Provider를 고를 수는 없다.
전략이 실제로 바꾸는 것은 "어느 단계를 AI에게 맡기고 어느 단계를 직접
줄 것인가"뿐이고, 화면은 그 이상을 약속하지 않는다.

"Unknown"도 없앤다. 개발 용어이고, 사용자가 할 수 있는 판단이 없다.
같은 사실을 사람의 말로 적는다 - 무료 / 약 $0.20 / 약 $0.80 이상 /
계산 불가.
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


class TestTheStrategyPanel(unittest.TestCase):

    def test_the_four_strategies_are_offered(self):
        page = _page()

        for label in ("완전 자동", "균형", "비용 절약", "내가 직접 제작"):
            with self.subTest(label=label):
                self.assertIn(label, page)

    def test_one_of_them_is_recommended(self):
        self.assertIn("추천", _page())

    def test_each_strategy_only_sets_defaults(self):
        """고른 뒤에도 단계마다 다시 바꿀 수 있어야 한다."""

        page = _page()
        block = _block(page, "function pickStrategy")

        # 전략은 기본값을 채우고 다시 그린다 - 잠그지 않는다.
        self.assertIn("uiPick", block)
        self.assertNotIn("disabled", block)

    def test_every_strategy_covers_the_four_stages(self):
        page = _page()
        block = _block(page, "const STRATEGIES", "\n];")

        for stage in ("script", "image", "voice", "metadata"):
            with self.subTest(stage=stage):
                self.assertGreaterEqual(block.count(stage + ":"), 4)

    def test_the_strategy_keys_are_real_option_keys(self):
        """전략이 없는 선택지를 가리키면 조용히 아무 일도 안 일어난다."""

        page = _page()
        ui = re.search(r"const STAGE_UI = \{(.*?)\n\};", page, re.S).group(1)
        keys = set(re.findall(r'\{key:"(\w+)"', ui))

        block = _block(page, "const STRATEGIES", "\n];")
        used = set(re.findall(r'(?:script|image|voice|metadata):\s*"(\w+)"',
                              block))

        self.assertTrue(used)
        for key in used:
            with self.subTest(key=key):
                self.assertIn(key, keys)

    def test_the_automation_share_of_each_strategy_is_declared(self):
        """100 / 75 / 50 / 25 / 0 이 아니라 실제 선택에서 계산한다."""

        page = _page()

        self.assertIn("function automationShare", page)


class TestTheCostWording(unittest.TestCase):

    def test_the_developer_word_is_gone(self):
        """사용자에게 보이는 글에서만 찾는다.

        왜 그 단어를 뺐는지 적어 둔 주석까지 걸면 설명을 지워야
        통과하는 테스트가 된다."""

        page = _page()
        visible = re.sub(r"^\s*//.*$", "", page, flags=re.M)
        visible = re.sub(r"/\*.*?\*/", "", visible, flags=re.S)

        self.assertNotIn("Unknown", visible)

    def test_the_four_states_exist(self):
        page = _page()
        block = _block(page, "function costWording")

        for wording in ("무료", "이상", "계산 불가", "약 $"):
            with self.subTest(wording=wording):
                self.assertIn(wording, block)

    def test_a_stage_that_calls_no_api_is_not_counted_as_unpriced(self):
        """배경음악은 Provider가 없어 계획에서 unknown으로 오지만,
        실제로는 assets/music/의 mp3라 돈이 나가지 않는다. 그것 때문에
        "무료"가 영영 안 나오면 안 된다."""

        plan = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "manual", "image": "import",
                                 "voice": "import", "metadata": "generate",
                                 "music": "generate"}},
        ).json()

        self.assertIn("music", plan["cost"]["unknown_stages"])

        page = _page()
        block = _block(page, "function unpricedStages")

        self.assertIn("engine.calls_api", block)

    def test_the_card_says_which_stages_cannot_be_priced(self):
        page = _page()
        block = _block(page, "function summaryCards", "\nasync function ")

        self.assertIn("unpriced", block)


class TestTheStageHeader(unittest.TestCase):

    def test_each_stage_carries_a_one_line_summary(self):
        page = _page()
        block = _block(page, "function renderStagePicks", "\nfunction ")

        self.assertIn("stageSummary", page)
        self.assertIn("stageSummary", block)

    def test_the_summary_is_built_from_the_options_themselves(self):
        """따로 적어 두면 선택지가 늘어날 때 한쪽만 낡는다."""

        page = _page()
        block = _block(page, "function stageSummary")

        self.assertIn("STAGE_UI", block)


class TestTheCardColours(unittest.TestCase):
    """색만 봐도 현재 상태를 알 수 있게."""

    def test_every_kind_has_its_own_class(self):
        page = _page()

        for cls in ("k-auto", "k-given", "k-off", "k-soon"):
            with self.subTest(cls=cls):
                self.assertIn(cls, page)

    def test_the_classes_are_styled(self):
        page = _page()
        style = page[page.index("<style>"):page.index("</style>")]

        for cls in ("k-auto", "k-given", "k-off", "k-soon"):
            with self.subTest(cls=cls):
                self.assertIn("." + cls, style)

    def test_the_kind_comes_from_the_source_mode(self):
        page = _page()
        block = _block(page, "function cardKind")

        for mode in ("generate", "import", "manual", "none"):
            with self.subTest(mode=mode):
                self.assertIn(mode, block)


class TestTheSummaryHasFiveCards(unittest.TestCase):

    def test_the_five_labels(self):
        page = _page()
        block = _block(page, "function summaryCards", "\nasync function ")

        for label in ("품질", "예상 시간", "예상 비용", "자동 생성 비율",
                      "API"):
            with self.subTest(label=label):
                self.assertIn(label, block)

    def test_the_share_is_a_percentage_of_the_stages_being_made(self):
        page = _page()
        block = _block(page, "function automationShare")

        self.assertIn("generate", block)
        self.assertIn("none", block)


class TestTheCurrentChoiceCard(unittest.TestCase):
    """우측 상단에 지금 고른 방식이 항상 보인다."""

    def test_it_shows_the_choice_not_only_the_engine(self):
        """Sprint117은 엔진 이름만 보여 줬다 - 이미지를 직접 업로드로
        바꿔도 "Imagen 4.0"이라고 적혀 있었다."""

        page = _page()
        block = _block(page, "function renderCurrentProviders")

        self.assertIn("uiPick", block)

    def test_it_is_redrawn_when_a_stage_changes(self):
        page = _page()
        block = _block(page, "async function pickStage", "\nfunction ")

        self.assertIn("renderCurrentProviders", block)


class TestNothingBehindTheScreenMoved(unittest.TestCase):
    """UI 표시만 바꾼다 - Plan도 그대로다."""

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
                self.assertNotIn("전략", source)
                self.assertNotIn("studio", source)

    def test_the_plan_contract_is_unchanged(self):
        """전략은 화면 안에서만 산다 - 서버는 여전히 selections만 받는다."""

        response = client.post(
            "/studio/api/production/plan",
            json={"selections": {"script": "generate"}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("strategy", response.json())

    def test_the_generate_button_still_posts_the_same_job(self):
        page = _page()

        self.assertIn('id="go"', page)
        self.assertIn("/studio/api/jobs", page)


if __name__ == "__main__":
    unittest.main()
