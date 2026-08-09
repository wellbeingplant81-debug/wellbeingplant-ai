"""
Sprint181 - 막혔을 때 스스로 알아볼 수 있게 (Epic 59, Phase 4).

Sprint180이 "지금 어디에 있는가"를 만들었다. 그런데 막힌 사람에게
필요한 것은 그 한 줄이 아니라 셋이다.

    무엇이 문제인가
    어떻게 하면 되는가
    안 되면 무엇을 보내면 되는가

새로 판정하지 않는다
--------------------
전부 이미 나온 답을 옮긴다.

    onboarding_state   지금 어디에 있는가, 무엇이 걸렸는가
    beta_telemetry     마지막에 무엇에 걸렸는가
    beta_feedback      보낼 것 한 덩이

여기서 문제를 새로 찾아내면, 화면이 말하는 문제와 실제로 막는 것이
달라진다. 그때 사람은 있지도 않은 것을 고치려 든다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app_info
from app.routers import studio as studio_router
from app.services import (
    beta_telemetry, free_workspace, onboarding_state, output_check,
    troubleshooting,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.root = os.path.join(self.home, "내자료")
        self.project = os.path.join(self.home, "프로젝트")
        self.store = os.path.join(self.home, "기억.json")

        os.makedirs(self.project)

        patched = patch.dict(os.environ,
                             {"AI_STUDIO_HOME": self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def workspace(self):
        for kind in ("images", "voices"):
            os.makedirs(os.path.join(self.root, kind), exist_ok=True)

        free_workspace.remember(self.store, self.root)

    def script(self, count=2):
        """관문에 맞춘 대본. 짧으면 품질 검사가 먼저 걸린다."""

        from app.services import duration_estimator, duration_optimizer

        bodies = [f"{n}번째 동작입니다" for n in range(1, count + 1)]
        at = 0

        while sum(duration_estimator.estimate_duration(b) for b in bodies) \
                < duration_optimizer.TARGET_DURATION_SECONDS:
            bodies[at % count] += " 무릎을 천천히 펴 주세요"
            at += 1

        scenes = [{"scene": n, "narration": bodies[n - 1],
                   "image_prompt": f"동작{n} 스트레칭"}
                  for n in range(1, count + 1)]

        with open(os.path.join(self.project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "무릎", "hook": "2분", "script": "본문",
                       "character": "40대 남성", "scenes": scenes}, f,
                      ensure_ascii=False)

        return scenes

    def made(self, *kinds, count=2):
        for number in range(1, count + 1):
            if "image" in kinds:
                path = os.path.join(self.project, "images",
                                    f"scene{number}.png")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").write(b"0" * 100)

            if "voice" in kinds:
                path = os.path.join(self.project, "audio", "scenes",
                                    f"scene{number}.wav")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").write(b"0" * 100)

        if "video" in kinds:
            path = os.path.join(self.project, *output_check.VIDEO_RELATIVE)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(b"0" * 5000)

    def now(self, project_path=None):
        return troubleshooting.build(self.store, project_path)


class ProblemTest(unittest.TestCase):
    """말이 되는가."""

    def test_every_state_has_something_to_do(self):
        """
        어느 상태에서 열어도 할 말이 있다.

        문제 해결 화면을 열었는데 비어 있으면, 사람은 그 화면을 두 번
        열지 않는다.
        """

        for state in onboarding_state.SAYS:
            with self.subTest(state=state):
                self.assertIn(state, troubleshooting.HOW)
                self.assertTrue(troubleshooting.HOW[state])


class WhereTest(Base):
    """1. 상태별로 무엇을 말하는가."""

    def test_the_first_run_is_told_what_to_do(self):
        """
        처음 켠 사람에게는 '문제'가 없다. 아직 아무것도 안 했을 뿐이다.

        여기서 없는 문제를 지어내면, 사람은 고칠 것이 있다고 생각하고
        찾아 헤맨다. 대신 무엇을 하면 되는지는 반드시 있어야 한다.
        """

        found = self.now()

        self.assertEqual(found["status"], onboarding_state.FIRST_RUN)
        self.assertEqual(found["problems"], [])
        self.assertTrue(found["message"])
        self.assertTrue(found["suggestions"])
        self.assertTrue(any("폴더" in line for line in found["suggestions"]))

    def test_a_missing_script_is_told(self):
        self.workspace()

        found = self.now(self.project)

        self.assertEqual(found["status"], onboarding_state.SCRIPT_REQUIRED)
        self.assertTrue(any("대본" in line for line in found["suggestions"]))

    def test_missing_assets_name_the_scene(self):
        """
        "Scene 3 이미지가 필요합니다"처럼 어디인지 말한다.

        그 문장은 final_check가 이미 만든 것이다 - 여기서 다시 짓지
        않는다.
        """

        self.workspace()
        self.script(count=3)

        found = self.now(self.project)

        self.assertEqual(found["status"], onboarding_state.ASSET_REQUIRED)
        self.assertTrue(any("Scene" in line for line in found["problems"]),
                        found["problems"])

    def test_a_finished_video_says_so(self):
        self.workspace()
        self.script()
        self.made("image", "voice", "video")

        with patch.object(output_check, "build",
                          return_value={"state": output_check.READY,
                                        "issues": [], "video": {}}):
            found = self.now(self.project)

        self.assertEqual(found["status"], onboarding_state.COMPLETED)
        self.assertEqual(found["problems"], [])
        self.assertTrue(found["suggestions"])

    def test_a_failed_render_points_at_the_result(self):
        self.workspace()
        self.script()
        self.made("image", "voice", "video")

        with patch.object(output_check, "build",
                          return_value={"state": output_check.FAILED,
                                        "issues": [{"message":
                                                    "Scene 2 이미지 없음"}],
                                        "video": {}}):
            found = self.now(self.project)

        self.assertEqual(found["status"], onboarding_state.FAILED)
        self.assertIn("Scene 2 이미지 없음", found["problems"])
        self.assertTrue(any("결과" in line
                            for line in found["suggestions"]))

    def test_the_last_error_is_carried_over(self):
        """
        마지막에 무엇에 걸렸는지도 함께 보여 준다.

        지금은 멀쩡해 보여도 방금 실패한 적이 있으면, 그것이 단서다.
        """

        beta_telemetry.failed(FileNotFoundError("없다"))

        found = self.now()

        self.assertEqual(found["last_error_kind"], "FileNotFoundError")


class AgreementTest(Base):
    """2. 기존 판정과 같은 말을 한다."""

    def test_the_status_is_exactly_the_onboarding_state(self):
        """
        여기서 다른 상태를 말하면, 진행 표시와 문제 해결이 서로 다른
        이야기를 한다.
        """

        self.workspace()
        self.script()

        for made in ((), ("image",), ("image", "voice")):
            with self.subTest(made=made):
                self.made(*made)

                mine = self.now(self.project)
                theirs = onboarding_state.build(self.store, self.project)

                self.assertEqual(mine["status"], theirs["state"])
                self.assertEqual(mine["problems"], theirs["reasons"])

    def test_it_judges_nothing_by_itself(self):
        import re

        source = os.path.join(REPO, "app", "services", "troubleshooting.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for wanted in ("onboarding_state", "beta_telemetry"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        for forbidden in ("open(", "makedirs", "generate_", "os.walk",
                          "os.path.exists"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class MakesNothingTest(Base):
    """3. 물어봤다고 만들지 않는다."""

    def test_no_maker_is_called(self):
        from app.services import studio_jobs, studio_review

        self.workspace()
        self.script()

        with patch.object(studio_review, "generate_script") as script, \
                patch.object(studio_review, "generate_images") as images, \
                patch.object(studio_review, "generate_voices") as voices, \
                patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            self.now(self.project)

            for maker in (script, images, voices, render, start):
                with self.subTest(maker=maker):
                    maker.assert_not_called()

    def test_nothing_new_is_written(self):
        self.workspace()
        self.script()

        before = sorted(os.listdir(self.project))

        self.now(self.project)

        self.assertEqual(sorted(os.listdir(self.project)), before)


class PrivacyTest(Base):
    """4. 보낼 글에 남의 것이 없다."""

    def test_the_contact_text_carries_no_personal_data(self):
        """
        문의 글은 그대로 밖으로 나간다.

        어느 상태에서 만들어도 경로나 이름이 섞이지 않아야 한다 -
        섞이면 그 사람은 제 폴더 구조를 모르는 사람에게 보내게 된다.
        """

        self.workspace()
        self.script(count=3)

        for project in (None, self.project):
            with self.subTest(project=bool(project)):
                text = self.now(project)["contact_text"]

                self.assertIn(app_info.VERSION, text)

                for leak in (self.home, self.root, self.project,
                             os.path.expanduser("~"),
                             os.environ.get("USERNAME") or "USERNAME",
                             "C:\\", ".png", ".mp4", "Traceback"):
                    with self.subTest(leak=leak):
                        self.assertNotIn(leak, text)

    def test_the_contact_text_says_where_to_send_it(self):
        text = self.now()["contact_text"]

        self.assertIn(app_info.CONTACT, text)

    def test_the_problems_are_in_the_text(self):
        """
        보낼 글에 지금 막힌 것이 들어 있다.

        따로 적게 하면 사람은 "안 돼요"라고만 보낸다.
        """

        self.workspace()
        self.script(count=3)

        found = self.now(self.project)

        self.assertTrue(found["problems"])

        for line in found["problems"][:3]:
            with self.subTest(line=line):
                self.assertIn(line, found["contact_text"])


class ApiTest(Base):
    """5. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

        self._project = studio_router._project_path
        self._store = studio_router._workspace_store

        studio_router._project_path = lambda project_id: self.project
        studio_router._workspace_store = lambda: self.store

        self.addCleanup(self._restore)

    def _restore(self):
        studio_router._project_path = self._project
        studio_router._workspace_store = self._store

    def test_it_answers_with_the_declared_fields(self):
        answer = self.client.get("/studio/api/troubleshooting")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("status", "problems", "suggestions", "contact_text"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_it_follows_the_person(self):
        self.assertEqual(
            self.client.get("/studio/api/troubleshooting").json()["status"],
            onboarding_state.FIRST_RUN)

        self.workspace()
        self.script()

        self.assertEqual(
            self.client.get(
                "/studio/api/troubleshooting?project_id=p1").json()["status"],
            onboarding_state.ASSET_REQUIRED)

    def test_an_unknown_project_does_not_blow_up(self):
        studio_router._project_path = self._project

        answer = self.client.get(
            "/studio/api/troubleshooting?project_id=없는것")

        self.assertEqual(answer.status_code, 200)

    def test_the_screen_has_the_place(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/troubleshooting", page)
        self.assertIn("문제 해결", page)
        self.assertIn("해결 방법", page)
        self.assertIn("문의하기", page)


if __name__ == "__main__":
    unittest.main()
