"""
Sprint183 - 처음 쓰는 사람의 여섯 걸음 (Epic 59, Phase 6).

Sprint180이 열 가지 상태를 만들었다. 그것은 우리에게 정확하지만,
처음 쓰는 사람에게는 낱말이 낯설다 - ASSET_REQUIRED가 무엇인지
모르는 사람에게 그 말은 아무것도 알려 주지 않는다.

그래서 여섯 걸음으로 다시 적는다
--------------------------------
    1. 프로그램 시작
    2. 내 자료 연결
    3. 대본 준비
    4. 자료 확인
    5. 제작 시작
    6. 결과 확인

새로 판정하지 않는다
--------------------
어느 걸음까지 왔는지는 onboarding_state가 낸 답에서 나온다. 여기서
다시 세면 진행 표시와 안내 카드가 서로 다른 걸음을 가리킨다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import studio as studio_router
from app.services import (
    first_run_guide, free_workspace, onboarding_state, output_check,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.root = os.path.join(self.home, "내자료")
        self.project = os.path.join(self.home, "프로젝트")
        self.store = os.path.join(self.home, "기억.json")

        os.makedirs(self.project)

        patched = patch.dict(os.environ, {"AI_STUDIO_HOME": self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def workspace(self):
        for kind in ("images", "voices"):
            os.makedirs(os.path.join(self.root, kind), exist_ok=True)

        free_workspace.remember(self.store, self.root)

    def script(self, count=2):
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
            json.dump({"title": "무릎 스트레칭 비법", "hook": "2분",
                       "script": "본문", "character": "40대 남성",
                       "scenes": scenes}, f, ensure_ascii=False)

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
        return first_run_guide.build(self.store, project_path)


class ShapeTest(Base):
    """1. 여섯 걸음."""

    def test_the_six_steps_are_the_declared_ones(self):
        found = self.now()

        self.assertEqual([step["title"] for step in found["steps"]],
                         ["프로그램 시작", "내 자료 연결", "대본 준비",
                          "자료 확인", "제작 시작", "결과 확인"])

        self.assertEqual([step["step"] for step in found["steps"]],
                         [1, 2, 3, 4, 5, 6])

    def test_every_step_carries_the_declared_fields(self):
        for step in self.now()["steps"]:
            with self.subTest(step=step["step"]):
                self.assertEqual(
                    sorted(step),
                    ["action", "completed", "description", "step", "title"])
                self.assertTrue(step["title"])
                self.assertTrue(step["description"])
                self.assertTrue(step["action"])


class ProgressTest(Base):
    """2. 걸음이 앞으로 간다."""

    def test_the_first_step_is_already_done(self):
        """
        프로그램을 켠 것이 첫 걸음이다.

        이 화면을 보고 있다는 것이 그 증거다 - 물어볼 것이 없다.
        """

        found = self.now()

        self.assertTrue(found["steps"][0]["completed"])
        self.assertEqual(found["current"], 2)

    def test_choosing_a_folder_moves_it(self):
        self.workspace()

        found = self.now(self.project)

        self.assertTrue(found["steps"][1]["completed"])
        self.assertEqual(found["current"], 3)

    def test_a_script_moves_it(self):
        self.workspace()
        self.script()

        found = self.now(self.project)

        self.assertTrue(found["steps"][2]["completed"])
        self.assertEqual(found["current"], 4)

    def test_assets_move_it(self):
        self.workspace()
        self.script()
        self.made("image", "voice")

        found = self.now(self.project)

        self.assertTrue(found["steps"][3]["completed"])
        self.assertEqual(found["current"], 5)

    def test_a_finished_video_completes_everything(self):
        self.workspace()
        self.script()
        self.made("image", "voice", "video")

        with patch.object(output_check, "build",
                          return_value={"state": output_check.READY,
                                        "issues": [], "video": {}}):
            found = self.now(self.project)

        self.assertTrue(all(step["completed"] for step in found["steps"]))
        self.assertIsNone(found["current"])
        self.assertTrue(found["done"])

    def test_a_script_that_needs_work_stays_at_three(self):
        """
        대본이 있어도 쓸 만하지 않으면 3단계다.

        파일이 있다는 것과 준비됐다는 것은 다르다.
        """

        self.workspace()
        self.script(count=1)

        with patch.object(onboarding_state, "build", return_value={
                "state": onboarding_state.SCRIPT_CHECK_REQUIRED,
                "title": "t", "message": "m", "next_action": "a",
                "can_continue": False, "reasons": ["짧습니다"],
                "steps": [{"key": "workspace", "label": "자료 연결",
                           "done": True},
                          {"key": "script", "label": "대본 준비",
                           "done": True},
                          {"key": "image", "label": "이미지", "done": False},
                          {"key": "voice", "label": "음성", "done": False},
                          {"key": "video", "label": "영상", "done": False},
                          {"key": "output", "label": "결과", "done": False}]}):

            found = self.now(self.project)

        self.assertEqual(found["current"], 3)
        self.assertFalse(found["steps"][2]["completed"])


class HeadlineTest(Base):
    """3. 사람이 읽는 한 줄."""

    def test_it_says_which_step_and_what_to_do(self):
        found = self.now()

        self.assertIn("2단계", found["headline"])
        self.assertIn("폴더", found["headline"])

    def test_the_script_step_names_the_chat_windows(self):
        self.workspace()

        found = self.now(self.project)

        self.assertIn("3단계", found["headline"])
        self.assertIn("Claude", found["headline"])
        self.assertIn("Gemini", found["headline"])

    def test_a_finished_one_says_so_without_a_step(self):
        self.workspace()
        self.script()
        self.made("image", "voice", "video")

        with patch.object(output_check, "build",
                          return_value={"state": output_check.READY,
                                        "issues": [], "video": {}}):
            found = self.now(self.project)

        self.assertNotIn("단계입니다", found["headline"])


class AgreementTest(Base):
    """4. 기존 판정과 같은 말을 한다."""

    def test_it_never_disagrees_with_onboarding(self):
        self.workspace()
        self.script()

        for made in ((), ("image",), ("image", "voice")):
            with self.subTest(made=made):
                self.made(*made)

                mine = self.now(self.project)
                theirs = onboarding_state.build(self.store, self.project)

                self.assertEqual(mine["state"], theirs["state"])

                # 만들 수 있는 상태면 자료 확인까지는 끝나 있다.
                if theirs["state"] == onboarding_state.READY:
                    self.assertTrue(mine["steps"][3]["completed"])

    def test_it_judges_nothing_by_itself(self):
        import re

        source = os.path.join(REPO, "app", "services", "first_run_guide.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        self.assertIn("onboarding_state", code)

        for forbidden in ("open(", "makedirs", "generate_", "os.walk",
                          "os.path.exists"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class QuietTest(Base):
    """5. 읽기만 한다."""

    def test_nothing_is_written(self):
        self.workspace()
        self.script()

        before = sorted(os.listdir(self.project))

        self.now(self.project)

        self.assertEqual(sorted(os.listdir(self.project)), before)

    def test_no_maker_is_called(self):
        from app.services import studio_jobs, studio_review

        self.workspace()
        self.script()

        with patch.object(studio_review, "generate_script") as script, \
                patch.object(studio_review, "generate_images") as images, \
                patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            self.now(self.project)

            for maker in (script, images, render, start):
                with self.subTest(maker=maker):
                    maker.assert_not_called()

    def test_no_personal_data(self):
        self.workspace()
        self.script()

        body = json.dumps(self.now(self.project), ensure_ascii=False)

        for leak in (self.home, self.root, self.project,
                     os.environ.get("USERNAME") or "USERNAME",
                     "무릎 스트레칭 비법", "내자료"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))


class ApiTest(Base):
    """6. 서버와 화면."""

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

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/first-run-guide")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("steps", "current", "headline", "state", "done"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_it_follows_the_person(self):
        self.assertEqual(
            self.client.get("/studio/api/first-run-guide").json()["current"],
            2)

        self.workspace()

        self.assertEqual(
            self.client.get(
                "/studio/api/first-run-guide?project_id=p1").json()["current"],
            3)

    def test_an_unknown_project_does_not_blow_up(self):
        studio_router._project_path = self._project

        answer = self.client.get(
            "/studio/api/first-run-guide?project_id=없는것")

        self.assertEqual(answer.status_code, 200)

    def test_the_screen_has_the_card(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/first-run-guide", page)
        self.assertIn("처음이신가요", page)


if __name__ == "__main__":
    unittest.main()
