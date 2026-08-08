"""
Sprint155 - 한 화면에서 무료 제작 준비를 끝낸다 (Epic 57, Phase 6).

Sprint150~154가 조각을 하나씩 만들었다. 쓸 수는 있었지만 순서를
사람이 외워야 했다 - 요청문을 어디서 만들고, 붙여넣은 다음 무엇을
누르고, 자료는 언제 훑는지.

이 Sprint는 새 기능을 만들지 않는다. 있는 것을 순서대로 잇는다.

    STEP 1  주제
    STEP 2  요청문 만들기 · 복사      script_prompt_builder
    STEP 3  대본 붙여넣기             chat_import
    STEP 4  내 자료 폴더 확인          free_workspace
    STEP 5  준비 상태 확인             requirements

무엇을 지키는가
---------------
    1. 그 순서가 실제로 이어진다      test_free_wizard_flow
    2. 그 길에서 밖으로 안 나간다     test_free_wizard_no_external_api
    3. 단계마다 상태를 바르게 읽는다  test_free_wizard_state
    4. 고른 Provider가 유지된다       test_free_wizard_keeps_provider

첫째가 이 Sprint의 값어치다. 화면이 부르는 그 순서를 그대로 눌러
봐야, 중간에 끊긴 자리가 드러난다.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app.main import app
from app.routers import studio as studio_router
from app.services import local_library, provider_selection

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _script_source():
    with open(PAGE, encoding="utf-8") as f:
        page = f.read()

    return page[page.index("<script>"):]


def _png(path):
    from PIL import Image

    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (64, 64), (180, 60, 60)).save(path)


def _tone(path, seconds=0.4):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", path],
        capture_output=True, check=True,
    )


def _mp4(path, seconds=0.4):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c=cyan:s=160x120:d={seconds}", "-pix_fmt", "yuv420p",
         path],
        capture_output=True, check=True,
    )


class WizardFlowBase(unittest.TestCase):
    """화면이 부르는 그 순서를 그대로 눌러 본다."""

    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="ws_")
        self.project = tempfile.mkdtemp(prefix="proj_")
        self.store = os.path.join(
            tempfile.mkdtemp(), ".workflow", "free_workspace.json")

        for path in (self.workspace, self.project,
                     os.path.dirname(os.path.dirname(self.store))):
            self.addCleanup(shutil.rmtree, path, ignore_errors=True)

        self.client = TestClient(app)

        self._real_project = studio_router._project_path
        self._real_store = studio_router._workspace_store

        studio_router._project_path = lambda project_id: self.project
        studio_router._workspace_store = lambda: self.store

        self.addCleanup(self._restore)

        self.topic = "40대 허리 건강 운동"

    def _restore(self):
        studio_router._project_path = self._real_project
        studio_router._workspace_store = self._real_store

    # ---- 화면이 부르는 것들 -------------------------------------------

    def step2_prompt(self, **kwargs):
        payload = {"topic": self.topic}
        payload.update(kwargs)

        return self.client.post("/studio/api/script-prompt", json=payload)

    def step3_paste(self, raw):
        """붙여넣은 것을 미리 본다. 아직 아무것도 만들지 않는다."""

        return self.client.post("/studio/api/production/import",
                                json={"raw": raw, "topic": self.topic})

    def step3_create(self, raw):
        """확정. 여기서 프로젝트가 생긴다."""

        return self.client.post("/studio/api/production/project",
                                json={"raw": raw, "topic": self.topic})

    def step4_workspace(self, root):
        return self.client.put("/studio/api/workspace", json={"root": root})

    def step4_scan(self):
        return self.client.post("/studio/api/review/p1/library", json={})

    def step5_requirements(self):
        return self.client.get("/studio/api/review/p1/requirements")

    def set_free_providers(self):
        return self.client.put("/studio/api/review/p1/providers", json={
            "providers": {"image": "local_stock", "voice": "local_voice"}})

    # ---- 답을 흉내 낸다 -----------------------------------------------

    def write_script(self, count=2):
        """
        붙여넣기가 끝난 상태를 만든다.

        답을 파서에 통과시킨 결과를 쓴다 - 실제 흐름이 그렇다.
        raw JSON을 그대로 script.json에 쓰면 image_prompt가 없는
        대본이 되고, 그것은 어느 경로로도 만들어지지 않는 모양이다.
        """

        from app.production.chat_script_parser import parse_script

        script = parse_script(self.answer(count))

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False)

        return script

    def answer(self, count=3):
        """요청문이 적어 준 뼈대를 그대로 채운 답."""

        return json.dumps({
            "title": "40대 허리, 이 동작 하나면 됩니다",
            "hook": "허리가 아프신가요?",
            "script": "전체 대본",
            "character": "40대 남성",
            "scenes": [
                {"scene": n, "narration": f"{n}번째 문장입니다.",
                 "subject": "40대 남성", "action": f"동작 {n}",
                 "environment": f"장소 {n}", "camera": "미디엄 샷",
                 "composition": "중앙", "lighting": "자연광"}
                for n in range(1, count + 1)
            ],
        }, ensure_ascii=False)

    def fill_workspace(self, images=(), videos=(), voices=()):
        for name in images:
            _png(os.path.join(self.workspace, "images", name))

        for name in videos:
            _mp4(os.path.join(self.workspace, "videos", name))

        for name in voices:
            _tone(os.path.join(self.workspace, "voices", name))


class FreeWizardFlowTest(WizardFlowBase):
    """1. 그 순서가 실제로 이어진다."""

    def test_free_wizard_flow(self):
        # STEP 2 - 요청문
        prompt = self.step2_prompt()

        self.assertEqual(prompt.status_code, 200)
        self.assertIn(self.topic, prompt.json()["prompt"])

        # STEP 3 - 붙여넣기. 미리 보기는 아무것도 만들지 않는다.
        raw = self.answer(3)
        before = sorted(os.listdir(self.project))

        preview = self.step3_paste(raw)

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["scene_count"], 3)
        self.assertEqual(sorted(os.listdir(self.project)), before)

        # 확정하면 프로젝트가 생긴다.
        created = self.step3_create(raw)

        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["project_id"])

        # 실제로 그 대본이 남았는가. 만든 곳은 진짜 경로이므로
        # 그쪽을 본다.
        with open(os.path.join(created.json()["project_path"], "script.json"),
                  encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(len(saved["scenes"]), 3)
        self.addCleanup(
            shutil.rmtree, created.json()["project_path"], ignore_errors=True)

        # 뒤 단계는 화면이 보고 있는 프로젝트를 쓴다.
        shutil.copy(
            os.path.join(created.json()["project_path"], "script.json"),
            os.path.join(self.project, "script.json"),
        )

        # STEP 4 - 내 자료 폴더
        self.fill_workspace(
            images=["동작 1.png", "동작 2.png"],
            videos=["동작 3.mp4"],
            voices=[f"scene{n}.wav" for n in (1, 2, 3)],
        )

        chosen = self.step4_workspace(self.workspace)

        self.assertEqual(chosen.status_code, 200)
        self.assertEqual(chosen.json()["counts"]["images"], 2)

        scanned = self.step4_scan()

        self.assertEqual(scanned.status_code, 200)

        # STEP 5 - 준비 상태
        report = self.step5_requirements().json()

        self.assertEqual(report["total"], 3)
        self.assertEqual(report["ready"]["images"], 3)
        self.assertEqual(report["ready"]["voice"], 3)
        self.assertEqual(report["ready"]["videos"], 1)

        missing = [r for r in report["requirements"]
                   if r["status"] == "missing"]

        self.assertEqual(missing, [])

    def test_a_bad_paste_stops_at_step_three(self):
        """읽지 못하는 것을 붙여넣으면 다음으로 못 간다."""

        response = self.step3_paste("이건 대본이 아니라 그냥 인사말입니다.")

        self.assertEqual(response.status_code, 400)

        # 사람이 고칠 수 있는 문장이어야 한다.
        self.assertTrue(response.json()["detail"].strip())

        # 프로젝트도 안 생긴다.
        self.assertFalse(
            os.path.exists(os.path.join(self.project, "script.json")))

    def test_an_empty_topic_stops_at_step_two(self):
        self.topic = "   "

        self.assertEqual(self.step2_prompt().status_code, 400)

    def test_a_missing_workspace_stops_at_step_four(self):
        self.assertEqual(
            self.step4_workspace(os.path.join(self.workspace, "없음"))
            .status_code, 400)

        # 안 골랐으면 훑을 수도 없다 - 무엇을 훑을지 모른다.
        self.assertEqual(self.step4_scan().status_code, 400)


class FreeWizardStateTest(WizardFlowBase):
    """3. 단계마다 상태를 바르게 읽는다."""

    def _state(self):
        """화면이 어디까지 왔는지 판단하는 근거 그대로."""

        return {
            "workspace": self.client.get("/studio/api/workspace").json(),
            "requirements": self.step5_requirements().json(),
        }

    def test_free_wizard_state(self):
        # 아무것도 안 했을 때 - 대본이 없으니 Scene이 0이다.
        state = self._state()

        self.assertIsNone(state["workspace"]["root"])
        self.assertEqual(state["requirements"]["total"], 0)
        self.assertFalse(state["requirements"]["scanned"])

        # 대본만 넣었을 때 - Scene은 생겼고 자료는 전부 없다.
        self.write_script(2)

        state = self._state()

        self.assertEqual(state["requirements"]["total"], 2)
        self.assertFalse(state["requirements"]["scanned"])
        self.assertEqual(state["requirements"]["ready"]["images"], 0)

        # 폴더만 골랐을 때 - 훑기 전에는 여전히 없다.
        self.fill_workspace(images=["동작 1.png"],
                            voices=["scene1.wav", "scene2.wav"])
        self.step4_workspace(self.workspace)

        state = self._state()

        self.assertEqual(state["workspace"]["root"], self.workspace)
        self.assertFalse(state["requirements"]["scanned"])

        # 훑고 나면 있는 것만 채워진다.
        self.step4_scan()
        state = self._state()

        self.assertTrue(state["requirements"]["scanned"])
        self.assertEqual(state["requirements"]["ready"]["images"], 1)
        self.assertEqual(state["requirements"]["ready"]["voice"], 2)

        missing = [
            r["required_asset"] for r in state["requirements"]["requirements"]
            if r["status"] == "missing"
        ]

        self.assertEqual(missing, ["image"])

        # 모자란 것을 알려 준 자리에 넣으면 끝난다.
        need = [r for r in state["requirements"]["requirements"]
                if r["status"] == "missing"][0]

        _png(os.path.join(need["expected_root"],
                          *need["expected_path"].split("/")))
        self.step4_scan()

        state = self._state()

        self.assertEqual(state["requirements"]["ready"]["images"], 2)
        self.assertEqual(
            [r for r in state["requirements"]["requirements"]
             if r["status"] == "missing"], [])

    def test_a_stale_error_does_not_survive_a_retry(self):
        """
        다시 훑을 때 지난번 오류를 지운다.

        안 지우면 자료를 다 채운 뒤에도 "폴더를 먼저 고르십시오"가
        남아, 다 됐는데 안 된 것처럼 보인다(실측에서 나왔다).
        """

        source = _script_source()

        for name in ("async function wizScan(){",
                     "async function wizChooseWorkspace(){"):
            with self.subTest(name=name):
                body = source[source.index(name):]
                body = body[:body.index("\n}")]

                self.assertIn('wizError = ""', body)

    def test_the_screen_reads_the_server_not_its_own_guess(self):
        """
        화면이 준비 여부를 스스로 세지 않는다.

        스스로 세면 서버가 아는 것과 갈리고, 사람은 화면이 초록인데
        렌더가 막히는 것을 보게 된다.
        """

        source = _script_source()

        # 위저드가 부르는 자리들.
        for path in ("/studio/api/script-prompt",
                     "/studio/api/production/import",
                     "/studio/api/production/project",
                     "/studio/api/workspace"):
            with self.subTest(path=path):
                self.assertIn(path, source)


class FreeWizardNoExternalApiTest(WizardFlowBase):
    """2. 그 길에서 밖으로 안 나간다."""

    def test_free_wizard_no_external_api(self):
        """
        STEP 1부터 5까지 어느 모델도 불리지 않는다.

        하나라도 불리면 "비용 0원"이 거짓이 된다.
        """

        import requests

        from app.providers import (
            local_stock_provider, local_voice_provider, tts_provider,
        )
        from app.services import asset_integration_service

        self.fill_workspace(
            images=["동작 1.png", "동작 2.png"],
            voices=["scene1.wav", "scene2.wav"],
        )

        with patch.object(requests, "get") as get, \
                patch.object(requests, "post") as post, \
                patch.object(requests, "request") as request, \
                patch.object(tts_provider, "generate_voice") as tts, \
                patch.object(
                    local_stock_provider, "generate_image") as make_image, \
                patch.object(
                    local_voice_provider, "generate_voice") as make_voice, \
                patch.object(
                    asset_integration_service, "get_candidates") as stock:

            self.step2_prompt(style="차분한", audience="40대")

            raw = self.answer(2)
            self.step3_paste(raw)

            created = self.step3_create(raw)
            self.addCleanup(shutil.rmtree, created.json()["project_path"],
                            ignore_errors=True)

            shutil.copy(
                os.path.join(created.json()["project_path"], "script.json"),
                os.path.join(self.project, "script.json"),
            )

            self.set_free_providers()
            self.step4_workspace(self.workspace)
            self.step4_scan()

            report = self.step5_requirements().json()

            for name, mock in (("requests.get", get), ("requests.post", post),
                               ("requests.request", request),
                               ("tts", tts), ("local_stock", make_image),
                               ("local_voice", make_voice),
                               ("stock 검색", stock)):
                with self.subTest(name=name):
                    mock.assert_not_called()

        # 그러면서도 실제로 답을 냈다.
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["ready"]["images"], 2)

    def test_the_wizard_never_asks_a_model_to_write(self):
        """
        화면에 "AI로 대본 만들기" 같은 자리가 생기지 않았다.

        무료 모드의 대본은 붙여넣기로만 온다 - 버튼 하나가 잘못
        들어가면 그 순간 돈이 든다.
        """

        source = _script_source()

        wizard = source[source.index("buildScriptPrompt"):]

        for path in ("/api/review/", "/script\"", "generate"):
            block = wizard[:wizard.index("function renderScriptBox")] \
                if "function renderScriptBox" in wizard else wizard

            with self.subTest(path=path):
                # 요청문을 만드는 자리는 대본 생성 API를 부르지 않는다.
                self.assertNotIn("api/review/{", block)


class FreeWizardKeepsProviderTest(WizardFlowBase):
    """4. 고른 Provider가 유지된다."""

    def test_free_wizard_keeps_provider(self):
        self.write_script(2)

        with open(os.path.join(self.project, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"topic": self.topic}, f, ensure_ascii=False)

        self.set_free_providers()

        # 파일에 남았는가.
        saved = provider_selection.all_selected(self.project)

        self.assertEqual(saved["image"], "local_stock")
        self.assertEqual(saved["voice"], "local_voice")

        # 뒤 단계를 지나도 그대로인가 - 훑기와 준비 상태 확인이
        # 고른 것을 지우지 않는다.
        self.fill_workspace(images=["동작 1.png"], voices=["scene1.wav"])
        self.step4_workspace(self.workspace)
        self.step4_scan()
        self.step5_requirements()

        after = provider_selection.all_selected(self.project)

        self.assertEqual(after["image"], "local_stock")
        self.assertEqual(after["voice"], "local_voice")

        # 다른 단계는 건드리지 않았다.
        self.assertEqual(after["script"], provider_selection.CURRENT)
        self.assertEqual(after["metadata"], provider_selection.CURRENT)

    def test_the_two_free_providers_are_selectable(self):
        """위저드가 고르는 이름이 실제로 붙어 있는 것들이다."""

        provider_selection.require_wired("image", "local_stock")
        provider_selection.require_wired("voice", "local_voice")

    def test_the_wizard_does_not_set_a_script_provider(self):
        """
        대본은 Provider가 아니라 붙여넣기다.

        chat_import는 만들지 않는 자리라 엔진이 아는 이름(WIRED)에
        없다. 라우터는 등록소 이름도 받아 주지만(Sprint139 - "골라
        두면 만들 때 정직하게 거절한다"), 위저드는 그 자리를 아예
        건드리지 않는다 - 붙여넣은 대본은 *_source가 기록하고,
        *_provider는 "누가 만드는가"의 칸이다. 둘을 섞으면 안 된다.
        """

        self.assertNotIn("chat_import", provider_selection.WIRED["script"])

        source = _script_source()
        wizard = source[source.index("function freeWizardProviders"):]
        body = wizard[:wizard.index("\n}")]

        # 이름을 여기 다시 적지 않는다 - 무료 모드 토글이 쓰는 그
        # 상수를 그대로 쓴다. 두 곳에 적으면 한쪽만 바뀌는 날이 온다.
        self.assertIn("FREE_IMAGE_PROVIDER", body)
        self.assertIn("FREE_VOICE_PROVIDER", body)

        self.assertNotIn("script", body)
        self.assertNotIn("chat_import", body)

        # 그 상수가 실제로 가리키는 것.
        for constant, expected in (("FREE_IMAGE_PROVIDER", "local_stock"),
                                   ("FREE_VOICE_PROVIDER", "local_voice")):
            with self.subTest(constant=constant):
                declared = re.search(
                    rf'const {constant} = "([^"]+)"', source,
                )

                self.assertIsNotNone(declared, f"{constant}가 없다")
                self.assertEqual(declared.group(1), expected)


if __name__ == "__main__":
    unittest.main()
