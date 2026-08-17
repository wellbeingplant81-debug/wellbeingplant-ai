"""
Sprint105 - 제작 방식 화면 (Epic 54, Phase 4).

사용자가 영상 생성 전에 제작 방식을 고른다. UI와 그것을 먹여 주는
엔드포인트 둘뿐이고, 파이프라인도 엔진도 Provider도 건드리지 않았다.

이 스프린트에서 확인한 구조적 사실 하나를 테스트로 남긴다 -
step01_script.run()은 기존 script.json을 읽는 분기가 없이 항상 새로
만든다. 그래서 붙여넣은 대본을 지금 저장해 두어도 영상 생성이
시작되는 순간 덮어써진다. 화면이 그 사실을 숨기지 않아야 한다.
"""

import ast
import os
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


class TestTheModeListIsServed(unittest.TestCase):

    def setUp(self):
        self.data = client.get("/studio/api/production/modes").json()

    def test_all_five_modes_are_offered(self):
        modes = [row["mode"] for row in self.data["modes"]]

        self.assertEqual(
            modes,
            ["auto_premium", "auto_standard", "auto_economy",
             "assisted", "manual"],
        )

    def test_each_mode_carries_a_label_and_description(self):
        for row in self.data["modes"]:
            with self.subTest(mode=row["mode"]):
                self.assertTrue(row["label"])
                self.assertTrue(row["description"])

    def test_the_current_engine_mode_is_reported(self):
        """지금 파이프라인이 하는 일이 어느 모드인지 화면이 알아야
        기본 선택을 할 수 있다."""

        self.assertEqual(self.data["current_engine_mode"], "auto_standard")

    def test_manual_is_marked_as_calling_no_api(self):
        by_mode = {row["mode"]: row for row in self.data["modes"]}

        self.assertFalse(by_mode["manual"]["calls_api"])
        self.assertTrue(by_mode["auto_premium"]["calls_api"])

    def test_premium_regenerates_and_economy_does_not(self):
        by_mode = {row["mode"]: row for row in self.data["modes"]}

        self.assertTrue(by_mode["auto_premium"]["auto_regenerate"])
        self.assertFalse(by_mode["auto_economy"]["auto_regenerate"])


class TestCostIsReportedHonestly(unittest.TestCase):
    """숫자를 지어내지 않는다."""

    def setUp(self):
        self.by_mode = {
            row["mode"]: row
            for row in client.get("/studio/api/production/modes").json()["modes"]
        }

    def test_auto_modes_report_which_stages_they_cannot_price(self):
        cost = self.by_mode["auto_standard"]["cost"]

        self.assertFalse(cost["complete"])
        self.assertEqual(
            sorted(cost["unknown_stages"]), ["image", "script", "voice"],
        )

    def test_metadata_is_known_to_be_free(self):
        """Sprint93의 메타데이터 엔진은 AI를 부르지 않는다."""

        cost = self.by_mode["auto_premium"]["cost"]
        metadata = [e for e in cost["estimates"] if e["stage"] == "metadata"][0]

        self.assertEqual(metadata["amount"], 0.0)

    def test_user_chosen_modes_have_no_precomputed_cost(self):
        """단계마다 사용자가 고르기 전에는 계산할 것이 없다."""

        for mode in ("assisted", "manual"):
            with self.subTest(mode=mode):
                self.assertIsNone(self.by_mode[mode]["cost"])

    def test_a_stage_without_a_provider_is_named(self):
        """music은 아직 담당 Provider가 없다. 조용히 빠뜨리지 않는다."""

        self.assertEqual(
            self.by_mode["auto_standard"]["missing_stages"], ["배경음악"],
        )


class TestTheImportEndpoint(unittest.TestCase):

    def _post(self, raw, topic=""):
        return client.post(
            "/studio/api/production/import", json={"raw": raw, "topic": topic},
        )

    def test_a_chat_style_paste_is_read(self):
        raw = ('물론입니다!\n\n```json\n'
               '{"title":"혈관 건강","scenes":[{"narration":"첫 문장."}]}\n'
               '```\n\n도움이 되셨길!')

        response = self._post(raw)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "혈관 건강")
        self.assertEqual(response.json()["scene_count"], 1)

    def test_the_topic_fills_a_missing_title(self):
        response = self._post('[{"narration":"문장."}]', topic="혈관 건강")

        self.assertEqual(response.json()["title"], "혈관 건강")

    def test_an_unreadable_paste_returns_the_parser_message(self):
        """사람이 읽고 고칠 수 있는 문장이 그대로 화면에 가야 한다."""

        response = self._post("안녕하세요! 무엇을 도와드릴까요?")

        self.assertEqual(response.status_code, 400)
        self.assertIn("구조를 찾지 못했습니다", response.json()["detail"])

    def test_an_empty_paste_is_refused(self):
        self.assertEqual(self._post("").status_code, 400)

    def test_the_preview_carries_the_derived_image_prompt(self):
        raw = ('{"title":"t","scenes":[{"narration":"문장.",'
               '"subject":"a man","action":"walking"}]}')

        scene = self._post(raw).json()["scenes"][0]

        self.assertIn("a man", scene["image_prompt"])

    def test_it_creates_no_project(self):
        """파이프라인의 step01이 기존 script.json을 읽는 분기 없이
        항상 새로 만든다 - 지금 저장해 두어도 덮어써진다."""

        from app.services import project_service

        before = sorted(os.listdir(project_service.OUTPUT_ROOT))

        self._post('{"title":"t","scenes":[{"narration":"문장."}]}')

        self.assertEqual(sorted(os.listdir(project_service.OUTPUT_ROOT)), before)


class TestStep01StillOnlyGenerates(unittest.TestCase):
    """Sprint105에는 "붙여넣기를 생성에 연결하지 못한 이유"였다.
    Sprint106의 Resolver와 Sprint107의 프로젝트 생성이 그 길을 열었다.

    step01 자체는 그대로다 - 여전히 기존 script.json을 읽지 않고
    항상 새로 만든다. 달라진 것은 그 앞에 Resolver가 섰다는 것뿐이다."""

    def test_step01_never_reads_an_existing_script(self):
        from app.steps import step01_script

        source = open(step01_script.__file__, encoding="utf-8").read()
        tree = ast.parse(source)

        reads = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "exists"
        ]

        self.assertEqual(reads, [])

    def test_the_screen_explains_the_three_steps(self):
        page = _page()

        self.assertIn("가져오기", page)
        self.assertIn("프로젝트 생성", page)
        self.assertIn("영상 생성", page)


class TestTheScreen(unittest.TestCase):

    def test_the_maker_panel_replaced_the_mode_panel(self):
        """Sprint116 - 등급을 먼저 고르게 하던 패널을 걷어냈다.

        제작 방식 자체가 없어진 것이 아니라, 단계마다 고르는 것으로
        옮겼다. 그 화면은 test_studio_ux2가 본다."""

        page = _page()

        self.assertNotIn('id="modes"', page)
        self.assertIn("새 영상 만들기", page)
        self.assertIn('id="stagePicks"', page)

    def test_the_paste_area_and_button_exist(self):
        page = _page()

        self.assertIn('id="importRaw"', page)
        self.assertIn("가져오기", page)
        self.assertIn("runImport", page)

    def test_the_manual_area_offers_a_file_and_a_textarea(self):
        page = _page()

        self.assertIn('id="manualFile"', page)
        self.assertIn('id="manualRaw"', page)

    def test_the_chat_import_guidance_names_the_models(self):
        page = _page()

        for model in ("ChatGPT", "Claude", "Gemini", "DeepSeek"):
            with self.subTest(model=model):
                self.assertIn(model, page)

    def test_the_cost_wording_matches_the_three_cases(self):
        """Sprint116 - 등급 카드마다 붙던 비용 줄이 요약 한 곳으로
        모였다. 세 경우(무료 / 금액 / 계산 불가)는 그대로다."""

        page = _page()

        # Sprint118 - "Unknown"을 없애면서 문구가 사람의 말로 바뀌었다.
        # 세 경우는 그대로다 - 무료 / 금액 / 계산 불가.
        self.assertIn("계산 불가", page)
        # Sprint168 - "무료"를 "API 비용 없음"으로 바꿨다.
        self.assertIn("API 비용 없음", page)
        self.assertIn("known.toFixed(2)", page)

    def test_the_existing_generate_button_is_untouched(self):
        page = _page()

        self.assertIn('id="go"', page)
        self.assertIn("영상 생성", page)


class TestNothingElseWasTouched(unittest.TestCase):
    """Acceptance - Pipeline/Engine/Provider/Stage 변경 금지."""

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

    def test_the_router_only_reads_the_production_package(self):
        """화면 전용 파서를 따로 만들지 않는다 - 실제 Provider가
        읽는다."""

        from app.routers import studio

        source = open(studio.__file__, encoding="utf-8").read()

        self.assertIn('_registry().get("script", "chat_import")', source)

    def test_the_global_registry_stays_empty(self):
        """app.main을 import하는 것만으로 등록이 일어나면 "등록은
        명시적으로 부를 때만"이라는 Sprint103의 계약이 깨진다."""

        from app.production.registry import default_registry

        self.assertEqual(len(default_registry()), 0)

    def test_the_generate_endpoint_gained_only_an_optional_project(self):
        """Sprint105에는 "모드 인자가 끼어들지 않았다"였다. Sprint107이
        미리 만들어 둔 프로젝트를 쓰게 하면서 선택 인자 하나를 더했다.
        Sprint218이 어느 단추로 눌렀는가와 과금 확인 여부를 더했다.

        지켜야 할 경계는 그대로다 - 주지 않으면 예전과 완전히 같다.
        새로 는 셋 다 기본값이 있어, 보내지 않는 호출부는 한 글자도
        영향받지 않는다."""

        from app.routers.studio import GenerateRequest

        self.assertEqual(
            sorted(GenerateRequest.model_fields),
            ["channel", "cost_ack", "creation_mode", "project_id", "topic"],
        )
        self.assertIsNone(GenerateRequest.model_fields["project_id"].default)
        self.assertIsNone(GenerateRequest.model_fields["creation_mode"].default)
        self.assertIs(GenerateRequest.model_fields["cost_ack"].default, False)

    def test_no_mode_reaches_the_engine(self):
        """
        Sprint105가 실제로 지킨 경계는 여기다 - **엔진의 부름말**에
        모드가 끼어들지 않는 것.

        요청 모델이 무엇을 더 받든, 파이프라인을 부르는 자리는
        topic·channel·project_id 셋이어야 한다. 그 셋을 넘어서는
        순간 "모드마다 엔진이 다르게 돈다"가 시작되고, 그러면 화면이
        약속한 것과 엔진이 하는 일이 갈라진다.

        문자열이 아니라 AST로 본다 - 설명 주석에 걸려 거짓 판정하는
        것을 이 저장소가 여러 번 겪었다.
        """

        import ast

        from app.services import studio_jobs

        tree = ast.parse(open(studio_jobs.__file__, encoding="utf-8").read())

        called = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "generate_short_video"
        ]

        self.assertTrue(called, "엔진을 부르는 자리를 못 찾았다")

        for call in called:
            given = sorted(kw.arg for kw in call.keywords)

            self.assertEqual(
                given, ["channel", "project_id", "topic"],
                f"엔진 부름말에 끼어든 것: {given}")
            self.assertEqual(call.args, [], "위치 인자가 끼어들었다")


if __name__ == "__main__":
    unittest.main()
