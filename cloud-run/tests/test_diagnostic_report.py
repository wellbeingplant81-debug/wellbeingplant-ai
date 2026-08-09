"""
Sprint182 - 문의할 때 그대로 보낼 것 (Epic 59, Phase 5).

Sprint181이 문제와 해결 방법을 만들어 줬다. 그런데 그것을 우리에게
보낼 때, 사람은 어느 화면의 무엇을 긁어야 하는지 또 골라야 했다.

한 덩이로 만든다. 누르면 복사되고, 붙여넣으면 우리가 읽는다.

경로를 담지 않는다
------------------
Sprint174의 [정보 복사]와 다른 자리다. 그쪽은 주인이 제 PC를 들여다
보는 글이라 내 것 자리와 도구 경로가 그대로 들어간다.

이것은 밖으로 나가는 글이다. 그래서 ffmpeg가 "있다/없다"만 적고
어디 있는지는 적지 않는다 - available()이 돌려주는 것은 경로이므로,
그대로 담으면 남의 PC 구조가 함께 나간다.

새로 판정하지 않는다
--------------------
    app_info           판번호
    onboarding_state   지금 어디에 있는가
    troubleshooting    무엇이 문제이고 어떻게 하면 되는가
    beta_telemetry     마지막에 무엇을 했는가
    media_tools        도구가 있는가
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
    beta_telemetry, diagnostic_report, free_workspace, media_tools,
    onboarding_state, output_check, troubleshooting,
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

    def script(self, count=3):
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

        return scenes

    def now(self, project_path=None):
        return diagnostic_report.build(self.store, project_path)


class ShapeTest(Base):
    """1. 무엇이 담기는가."""

    def test_it_carries_the_declared_fields(self):
        found = self.now()

        self.assertEqual(sorted(found),
                         sorted(diagnostic_report.FIELDS))

    def test_the_version_is_there(self):
        found = self.now()

        self.assertEqual(found["version"], app_info.VERSION)
        self.assertIn(app_info.VERSION, found["report"])

    def test_the_state_is_the_one_everyone_else_says(self):
        """
        여기서 다른 상태를 말하면, 받아 보는 우리가 화면과 다른 것을
        읽게 된다.
        """

        self.workspace()
        self.script()

        found = self.now(self.project)
        theirs = troubleshooting.build(self.store, self.project)

        self.assertEqual(found["current_state"], theirs["status"])
        self.assertEqual(found["problems"], theirs["problems"])
        self.assertEqual(found["suggestions"], theirs["suggestions"])

    def test_the_last_action_comes_from_the_record(self):
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        found = self.now()

        self.assertEqual(found["last_action"],
                         beta_telemetry.WORKSPACE_SELECTED)

    def test_the_problem_count_is_in_the_text(self):
        self.workspace()
        self.script()

        found = self.now(self.project)

        self.assertGreater(len(found["problems"]), 0)
        self.assertIn(str(len(found["problems"])), found["report"])


class EnvironmentTest(Base):
    """2. 도구가 있는가 - 어디 있는지는 적지 않는다."""

    def test_it_says_whether_the_tools_are_there(self):
        found = self.now()["environment"]

        for name in (media_tools.FFMPEG, media_tools.FFPROBE):
            with self.subTest(name=name):
                self.assertIn(name, found)
                self.assertIsInstance(found[name], bool)

    def test_a_missing_tool_is_said_plainly(self):
        with patch.object(media_tools, "available",
                          return_value={media_tools.FFMPEG: None,
                                        media_tools.FFPROBE: "C:\\x\\y.exe"}):
            found = self.now()

        self.assertFalse(found["environment"][media_tools.FFMPEG])
        self.assertTrue(found["environment"][media_tools.FFPROBE])

        # 있다고만 하고 어디 있는지는 말하지 않는다.
        self.assertNotIn("C:\\x\\y.exe", json.dumps(found,
                                                    ensure_ascii=False))

    def test_it_says_whether_music_is_there(self):
        found = self.now()["environment"]

        self.assertIn("music", found)
        self.assertIsInstance(found["music"], bool)


class PrivacyTest(Base):
    """3. 남의 것이 들어가지 않는다."""

    def test_nothing_personal_anywhere(self):
        """
        어느 상태에서 만들어도 경로·이름·제목이 섞이지 않는다.

        이 글은 그대로 밖으로 나간다.
        """

        beta_telemetry.failed(FileNotFoundError(
            r"C:\Users\사람\내 영상\무릎 스트레칭.png"))

        for project in (None, self.project):
            with self.subTest(project=bool(project)):
                if project:
                    self.workspace()
                    self.script()

                found = self.now(project)
                body = json.dumps(found, ensure_ascii=False)

                # 확장자를 맨 문자열로 찾지 않는다 - 해결 방법에 우리가
                # 쓴 예시 파일 이름이 들어 있다("예: 무릎 스트레칭.png").
                # 그것은 남의 것이 아니라 우리가 지은 안내다. 막으려는
                # 것은 그 사람의 자리와 이름이므로 그 모양으로 본다.
                for leak in (self.home, self.root, self.project,
                             os.path.expanduser("~"),
                             os.environ.get("USERNAME") or "USERNAME",
                             "무릎 스트레칭 비법", "Traceback",
                             "내자료", "프로젝트"):
                    with self.subTest(leak=leak):
                        self.assertNotIn(leak, body)
                        self.assertNotIn(leak, found["report"])

                # 어떤 절대 경로도 없다.
                import re

                for text in (body, found["report"]):
                    with self.subTest(text=text[:20]):
                        self.assertIsNone(
                            re.search(r"[A-Za-z]:[\\/]", text),
                            "절대 경로가 들어갔다")

    def test_the_project_name_is_not_carried(self):
        self.workspace()
        self.script()

        found = self.now(self.project)

        self.assertNotIn(os.path.basename(self.project),
                         json.dumps(found, ensure_ascii=False))


class ReadsOnlyTest(Base):
    """4. 읽기만 한다."""

    def test_nothing_is_written(self):
        self.workspace()
        self.script()

        before = sorted(os.listdir(self.project))
        home_before = sorted(os.listdir(self.home))

        self.now(self.project)

        self.assertEqual(sorted(os.listdir(self.project)), before)
        self.assertEqual(sorted(os.listdir(self.home)), home_before)

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

    def test_it_judges_nothing_by_itself(self):
        import re

        source = os.path.join(REPO, "app", "services",
                              "diagnostic_report.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for wanted in ("app_info", "troubleshooting", "beta_telemetry",
                       "media_tools"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        for forbidden in ("open(", "makedirs", "generate_", "os.walk",
                          "atomic_write"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


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

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/diagnostic-report")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in diagnostic_report.FIELDS:
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        self.workspace()
        self.script()

        found = self.client.get(
            "/studio/api/diagnostic-report?project_id=p1").json()

        self.assertEqual(found["current_state"],
                         onboarding_state.build(self.store,
                                                self.project)["state"])

    def test_an_unknown_project_does_not_blow_up(self):
        studio_router._project_path = self._project

        answer = self.client.get(
            "/studio/api/diagnostic-report?project_id=없는것")

        self.assertEqual(answer.status_code, 200)

    def test_the_screen_has_the_button(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/diagnostic-report", page)
        self.assertIn("진단 정보 복사", page)

    def test_the_screen_shows_it_when_the_clipboard_refuses(self):
        """
        복사가 막히면 글을 화면에 띄운다.

        눌렀는데 아무 일도 안 일어나면 사람은 고장 난 줄 안다.
        """

        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("copyDiagnostic", page)
        self.assertIn("직접 복사", page)


if __name__ == "__main__":
    unittest.main()
