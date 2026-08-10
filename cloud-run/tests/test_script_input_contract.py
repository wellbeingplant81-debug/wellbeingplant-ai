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

        self.addCleanup(self._forget_jobs)

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
    """2. 건드리지 않은 것."""

    def test_a_whole_script_still_starts(self):
        self.place(WHOLE)

        self.assertEqual(self.ask(self.project_id).status_code, 200)

    def test_without_a_project_it_is_unchanged(self):
        """
        AI가 대본을 쓰는 길. 아직 없는 대본을 미리 검사할 수 없다.
        """

        self.assertEqual(self.ask().status_code, 200)

    def test_a_project_without_a_script_is_unchanged(self):
        """
        script.json이 없으면 미리 놓인 대본을 쓰는 길이 아니다.
        """

        self.assertEqual(self.ask(self.project_id).status_code, 200)


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
