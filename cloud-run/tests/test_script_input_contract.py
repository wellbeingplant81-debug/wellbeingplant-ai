"""
Sprint203 - 대본 입력 계약을 제때 말한다 (Epic 59, Phase 20).

Sprint202 실측에서 렌더가 개발자 문구로 죽었다.

    script.json의 scene이 뒤 단계가 요구하는 값을 갖추지 못했습니다
    - scene 1: image_prompt 없음

사람이 읽을 말을 만들려다 알았다 - 이미 있다
--------------------------------------------
script_quality_check가 "Scene 1: 그림 묘사가 없습니다"라고 말하고,
onboarding_state가 그것을 "대본을 고쳐야 합니다"로 화면에 띄운다.
폴더를 고른 사람은 제작 시작 전에 그 말을 본다.

새 안내를 만들면 같은 말을 두 벌 갖게 된다.

구멍은 문지기가 화면에만 있다는 것이다
--------------------------------------
POST /api/jobs 는 부르기 전에 아무것도 보지 않는다. 화면이 버튼을
감출 뿐이고 그 아래 API는 누구에게나 열려 있다 - Sprint202의 smoke
test가 그 틈으로 들어갔다.

그래서 같은 프로그램이 같은 상태를 두 가지로 말한다.

    화면을 따라간 사람   "Scene 1: 그림 묘사가 없습니다" · 다음 행동 있음
    API를 직접 부른 사람  몇 초 뒤 "image_prompt 없음" · 다음 행동 없음

막는 기준은 계약이지 품질이 아니다
----------------------------------
script_quality_check로 막으면 "9초로 짧습니다"처럼 렌더가 견디는
것까지 막힌다. 어차피 죽었을 것만 더 일찍 막는다.

    막을지 말지   step01_script_resolve.validate()
    무슨 말을     script_quality_check.check()["reasons"]
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import runtime_paths
from app.services import studio_jobs

NO_IMAGE = {
    "title": "무릎 통증 완화 스트레칭",
    "hook": "",
    "script": "무릎이 아플 때",
    "scenes": [
        {"scene": 1, "narration": "무릎이 아플 때는 다리를 펴 주십시오."},
        {"scene": 2, "narration": "발목을 위아래로 열 번 움직이십시오."},
    ],
}

WHOLE = {
    "title": "무릎 통증 완화 스트레칭",
    "hook": "무릎이 아프십니까",
    "script": "무릎 스트레칭 안내",
    "character": "편안한 옷차림의 사람",
    "scenes": [
        {"scene": 1, "narration": "무릎이 아플 때는 다리를 펴 주십시오.",
         "image_prompt": "무릎을 펴고 앉은 사람"},
        {"scene": 2, "narration": "발목을 위아래로 열 번 움직이십시오.",
         "image_prompt": "발목을 움직이는 발"},
    ],
}


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

        # 만들어 둔 프로젝트를 흉내 낸다 - 붙여넣기가 놓아 둔 자리다.
        #
        # 라우터가 보는 그 자리에 놓는다. project_service.OUTPUT_ROOT는
        # 들일 때 한 번 정해지므로, 여기서 runtime_paths로 따로 지으면
        # 라우터와 다른 곳을 보게 된다.
        from app.services import project_service

        self.project_id = "20260810_203"

        rooted = patch.object(project_service, "OUTPUT_ROOT",
                              runtime_paths.ensure(
                                  os.path.join(self.home, "output")))
        rooted.start()
        self.addCleanup(rooted.stop)

        self.project = runtime_paths.ensure(
            os.path.join(project_service.OUTPUT_ROOT, self.project_id))

        # Sprint226 - 회귀는 실제 생성 엔진을 부르지 않는다.
        #
        # 결과를 지어내지 않는다. 문을 닫을 뿐이다 - 부르면 거절하고,
        # 부른 사실은 남긴다. 이 파일의 시험이 보는 것은 "작업이
        # 시작되는가"이고 그 판정은 요청이 200으로 받아들여지는 순간에
        # 끝난다. 그 뒤에 엔진이 무엇을 하는지는 여기서 볼 일이 아니다.
        #
        # 막지 않으면 이 세 시험이 실제로 Vertex를 부른다 - 회귀가 돈을
        # 쓰고, 답이 네트워크에 따라 흔들린다.
        self.engine_calls = []

        def refuse_to_run_the_engine(**asked):
            self.engine_calls.append(asked)

            raise RuntimeError("회귀에서는 실제 생성 엔진을 부르지 않습니다.")

        closed = patch("app.services.factory_service.generate_short_video",
                       refuse_to_run_the_engine)
        closed.start()
        self.addCleanup(closed.stop)

        self.addCleanup(self._forget_jobs)

        # 마지막에 적은 것이 가장 먼저 치워진다. 시작한 작업을 끝까지
        # 책임지는 일이 그 자리다 - 임시 집을 지우기 전에, 문을 다시
        # 열기 전에 끝나 있어야 한다.
        self.addCleanup(self._settle_jobs)

    def _settle_jobs(self):
        """시작한 작업이 끝난 뒤에 나간다. 안 끝나면 그렇다고 말한다."""

        left = studio_jobs.settle(timeout=30.0)

        self.assertEqual(
            left, [],
            f"시험이 끝났는데 아직 도는 작업이 있습니다: {left}")

    def _forget_jobs(self):
        studio_jobs._jobs.clear()

    def place(self, script):
        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False)

    def ask(self, project_id=None):
        body = {"topic": "무릎 통증 완화 스트레칭", "channel": "wellbeing"}

        if project_id:
            body["project_id"] = project_id

        return self.client.post("/studio/api/jobs", json=body)


class RefusedTest(Base):
    """1. 갖추지 못한 대본은 부르기 전에 막는다."""

    def test_it_is_refused(self):
        self.place(NO_IMAGE)

        answer = self.ask(self.project_id)

        self.assertEqual(answer.status_code, 400)

    def test_it_says_which_scene_in_words_a_person_reads(self):
        """
        개발자 문구가 아니라, 화면이 쓰는 그 말이어야 한다.
        """

        self.place(NO_IMAGE)

        said = self.ask(self.project_id).text

        self.assertIn("Scene 1: 그림 묘사가 없습니다", said)
        self.assertIn("Scene 2: 그림 묘사가 없습니다", said)
        self.assertNotIn("image_prompt", said)

    def test_it_says_what_to_do_next(self):
        self.place(NO_IMAGE)

        found = self.ask(self.project_id).json()

        said = json.dumps(found, ensure_ascii=False)

        self.assertIn("대본 고치기", said)

    def test_no_job_is_made(self):
        """
        막았다면서 작업을 만들어 두면, 큐에 죽을 것이 쌓인다.
        """

        self.place(NO_IMAGE)

        before = len(studio_jobs.recent(50))

        self.ask(self.project_id)

        self.assertEqual(len(studio_jobs.recent(50)), before)

    def test_the_script_is_not_touched(self):
        """
        지어 넣지 않는다. 사용자가 준 대본을 우리가 고치면 그것은 더
        이상 사용자가 준 대본이 아니다.
        """

        self.place(NO_IMAGE)

        path = os.path.join(self.project, "script.json")

        with open(path, encoding="utf-8") as f:
            before = f.read()

        self.ask(self.project_id)

        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)


class StillWorksTest(Base):
    """
    2. 건드리지 않은 것.

    Sprint226 - 보는 것을 한 가지 늘렸다. 200으로 받아들여지는 것만
    보면, 요청은 통과했는데 엔진까지 가지 않는 날에도 이 시험은
    통과한다. 실제로 무엇이 들어갔는지까지 본다 - 판정을 낮춘 것이
    아니라 올린 것이다.
    """

    def entered(self):
        """엔진 문 앞까지 실제로 갔는가. 문은 닫혀 있다(Base)."""

        studio_jobs.settle(timeout=30.0)

        return self.engine_calls

    def test_a_whole_script_still_starts(self):
        self.place(WHOLE)

        self.assertEqual(self.ask(self.project_id).status_code, 200)

    def test_a_whole_script_reaches_the_engine(self):
        self.place(WHOLE)
        self.ask(self.project_id)

        self.assertEqual(len(self.entered()), 1)

    def test_without_a_project_it_is_unchanged(self):
        """
        AI가 대본을 쓰는 길. 아직 없는 대본을 미리 검사할 수 없다.
        """

        self.assertEqual(self.ask().status_code, 200)

    def test_without_a_project_it_still_reaches_the_engine(self):
        self.ask()

        self.assertEqual(len(self.entered()), 1)

    def test_a_project_without_a_script_is_unchanged(self):
        """
        script.json이 없으면 미리 놓인 대본을 쓰는 길이 아니다.
        """

        self.assertEqual(self.ask(self.project_id).status_code, 200)

    def test_the_engine_is_asked_for_what_the_person_typed(self):
        """
        무엇을 들고 갔는지까지 본다. 주제가 바뀌어 들어가면 사람은
        시킨 적 없는 영상을 받는다.
        """

        self.ask(self.project_id)

        asked = self.entered()[0]

        self.assertEqual(asked["topic"], "무릎 통증 완화 스트레칭")
        self.assertEqual(asked["channel"], "wellbeing")


class TheScreenConnectsItTest(Base):
    """
    Sprint204 - 거절을 수정 행동으로 잇는다.

    Sprint203은 라우터만 고치고 화면을 보지 않았다. 제작 시작 단추가
    r.ok를 안 봐서, 400이 오면 job_id가 undefined인 채 "생성 중…"이라고
    적어 놓고 단추는 잠긴 채로 멈췄다 - 사람은 아무 일도 일어나지 않는
    화면을 보며 기다렸다.

    서버는 좋아지고 화면은 나빠졌다. 그것을 잇는다.
    """

    def page(self):
        from app.routers import studio as studio_router

        return studio_router.studio_page().body.decode("utf-8")

    def go_handler(self):
        """제작 시작 단추가 하는 일만 떼어 본다."""

        page = self.page()
        at = page.find('$("go").onclick')

        self.assertNotEqual(at, -1, "제작 시작 단추를 찾지 못했습니다")

        return page[at:at + 2400]

    def test_the_refusal_carries_a_name_not_only_words(self):
        """
        화면이 글자를 보고 무엇을 열지 정하면, 문구가 바뀌는 날
        조용히 틀린다.
        """

        from app.services import onboarding_state

        self.place(NO_IMAGE)

        found = self.ask(self.project_id).json()["detail"]

        self.assertEqual(found["state"],
                         onboarding_state.SCRIPT_CHECK_REQUIRED)

    def test_the_button_looks_at_whether_it_worked(self):
        self.assertIn("if(!r.ok)", self.go_handler())

    def test_the_button_comes_back(self):
        """
        잠긴 채로 두면 다시 눌러 볼 수도 없다.
        """

        said = self.go_handler()

        at = said.find("if(!r.ok)")

        self.assertNotEqual(at, -1)
        self.assertIn('$("go").disabled = false', said[at:])

    def test_it_does_not_say_it_is_making_something(self):
        """
        거절당했는데 "생성 중…"이라고 적어 두면, 사람은 아무 일도
        일어나지 않는 화면을 보며 기다린다.
        """

        said = self.go_handler()

        at = said.find("if(!r.ok)")

        self.assertIn("showScriptRefused", said[at:])
        self.assertIn("return", said[at:])

    def test_the_screen_shows_what_is_wrong(self):
        page = self.page()

        self.assertIn("showScriptRefused", page)
        self.assertIn("reasons", page[page.find("showScriptRefused"):])

    def test_the_screen_offers_the_way_to_fix_it(self):
        """
        고친 대본을 다시 붙여넣는 자리는 이미 있다(무료 제작 3단계).
        """

        page = self.page()

        at = page.find("function showScriptRefused")
        self.assertNotEqual(at, -1)

        said = page[at:at + 1800]

        self.assertIn("SCRIPT_CHECK_REQUIRED", said)
        self.assertIn("openScriptFix()", said)

        opener = page.find("function openScriptFix")
        self.assertNotEqual(opener, -1)

        self.assertIn("toggleFreeWizard", page[opener:opener + 600])
        self.assertIn("wizRaw", page[opener:opener + 600])


class TheWizardAsksFirstTest(Base):
    """
    Sprint205 - 붙여넣기 칸에서 미리 말한다.

    검사는 이미 있었다. POST /api/script-check 가 "Scene 1: 그림 묘사가
    없습니다"라고 말한다. 그런데 무료 제작 마법사의 붙여넣기 칸만 그
    검사를 부르지 않았다.

        checkScript('importRaw','importQuality')   있다
        checkScript('manualRaw','manualQuality')   있다
        wizRaw                                     없다

    하필 Closed Beta 사용자가 지나는 길이 그 길이다. 그래서 넷째
    걸음(제작 시작)에서야 알았다 - 첫째 걸음에서 이미 할 수 있던 말을.
    """

    def page(self):
        from app.routers import studio as studio_router

        return studio_router.studio_page().body.decode("utf-8")

    def test_the_wizard_asks_the_check_that_already_exists(self):
        self.assertIn("checkScript('wizRaw','wizQuality')", self.page())

    def test_there_is_a_place_to_show_the_answer(self):
        self.assertIn('id="wizQuality"', self.page())

    def test_the_box_says_what_a_script_must_have(self):
        """
        무엇이 있어야 하는지 모르면 붙여넣고 나서야 안다.
        """

        page = self.page()
        at = page.find('id="wizRaw"')

        self.assertNotEqual(at, -1)

        near = page[max(0, at - 900):at + 900]

        self.assertIn("읽을 문장", near)
        self.assertIn("그림 묘사", near)

    def test_those_words_are_the_words_the_check_uses(self):
        """
        검사와 안내가 다른 낱말을 쓰면, 안내를 보고 고쳐도 검사가
        여전히 안 된다고 한다.
        """

        from app.services import script_quality_check

        found = script_quality_check.check({
            "title": "무릎", "hook": "", "script": "무릎",
            "scenes": [{"scene": 1, "narration": "다리를 펴 주십시오."}],
        })

        said = " ".join(found.get("reasons") or [])

        self.assertIn("그림 묘사", said)

    def test_the_check_still_only_reads(self):
        """
        읽어 보는 것으로 프로젝트가 생기면 안 된다.
        """

        before = sorted(os.listdir(self.home))

        answer = self.client.post(
            "/studio/api/script-check",
            json={"raw": "제목: 무릎\n\nScene 1\n다리를 펴 주십시오.\n"})

        self.assertEqual(answer.status_code, 200)
        self.assertEqual(sorted(os.listdir(self.home)), before)


class NothingIsMadeTest(Base):
    """Sprint204 - 거절할 때 아무것도 만들지 않는다."""

    def test_no_provider_is_called(self):
        """
        안내를 하려고 AI를 부르면 그것은 안내가 아니라 생성이다.
        """

        from app.providers import tts_provider
        from app.services import image_service

        self.place(NO_IMAGE)

        with patch.object(image_service, "generate_image") as image, \
                patch.object(tts_provider, "generate_voice") as voice:

            self.ask(self.project_id)

            image.assert_not_called()
            voice.assert_not_called()

    def test_no_render_is_started(self):
        self.place(NO_IMAGE)

        with patch.object(studio_jobs, "start") as started:
            self.ask(self.project_id)

            started.assert_not_called()


class PrivacyTest(Base):
    """3. 거절하는 말에 남의 것이 실리지 않는다."""

    def test_no_path_and_no_traceback(self):
        self.place(NO_IMAGE)

        said = self.ask(self.project_id).text

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", said))
        self.assertNotIn("Traceback", said)
        self.assertNotIn(self.home, said)

    def test_no_file_names_of_the_user(self):
        """
        프로젝트 폴더 이름과 자료 파일 이름은 남의 것이다.
        """

        self.place(NO_IMAGE)

        stuff = runtime_paths.ensure(os.path.join(self.home, "내자료"))

        with open(os.path.join(stuff, "무릎 사진.png"), "wb") as f:
            f.write(b"x")

        said = self.ask(self.project_id).text

        self.assertNotIn("무릎 사진.png", said)
        self.assertNotIn(self.project_id, said)


if __name__ == "__main__":
    unittest.main()
