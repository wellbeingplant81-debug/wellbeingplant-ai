"""
Sprint189 - 피드백과 단계를 잇는다 (Epic 59, Phase 12).

사양은 "현재 단계별 의견 - 자료 연결 3건"을 그리라고 했다. 그런데
그 숫자를 만들 자료가 없다.

없는 것을 확인한 자리
---------------------
    피드백은 사람이 자유롭게 쓴 글 파일이다(Sprint174)
    그 글에 "나는 자료 연결에서 막혔다"고 적혀 있지 않다
    그 글을 읽지도 않는다 - 경로·파일명·내용이 전부 남의 것이다
    글과 기록을 짝지으면 그것이 곧 사용자 식별이다(§금지)

그래서 '의견 건수'를 지어내지 않는다. 대신 실제로 있는 것을 단계에
붙인다.

    그 단계에서 멈춘 설치본이 몇 벌인가   beta_dashboard
    그 단계에서 무슨 오류가 났는가        beta_dashboard
    내 피드백 폴더에 글이 몇 개 있는가    개수만, 이름도 내용도 안 봄

이름을 정확히 붙인다
--------------------
"의견 3건"이라고 부르면 누군가 그 셋을 읽으려 든다. 있는 것은
"그 단계에서 멈춘 설치본 3벌"이다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import runtime_paths
from app.routers import studio as studio_router
from app.services import (
    beta_dashboard, beta_feedback_loop, beta_telemetry,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def wrote(self, *names):
        """사람이 피드백 폴더에 글을 남겼다."""

        folder = runtime_paths.ensure(runtime_paths.feedback_root())

        for name in names:
            with open(os.path.join(folder, name), "w",
                      encoding="utf-8") as f:
                f.write("무릎 영상이 안 만들어집니다. "
                        r"C:\Users\사람\내자료 를 골랐습니다.")

    def sent(self, name, *events, error=None):
        folder = runtime_paths.ensure(beta_dashboard.collected_root())

        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "launch_count": 1,
                       "first_launch_at": None, "last_launch_at": None,
                       "events": [{"event": e,
                                   "timestamp": "2026-08-09T10:00:00",
                                   "version": "0.1.0"} for e in events],
                       "seen": [], "last_error_kind": error,
                       "last_error_time": None}, f, ensure_ascii=False)

    def now(self):
        return beta_feedback_loop.build()


class StageTest(Base):
    """1. 단계마다 무엇이 붙는가."""

    def test_every_stage_is_listed_even_when_empty(self):
        found = self.now()

        self.assertEqual([row["key"] for row in found["stages"]],
                         list(beta_dashboard.STAGES))

    def test_the_stopped_count_comes_from_the_dashboard(self):
        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED)
        self.sent("을.json", beta_telemetry.WORKSPACE_SELECTED)
        self.sent("병.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)

        stopped = {row["key"]: row["stopped"] for row in self.now()["stages"]}

        self.assertEqual(stopped[beta_dashboard.WORKSPACE_SELECTED], 2)
        self.assertEqual(stopped[beta_dashboard.SCRIPT_READY], 1)

    def test_the_errors_are_grouped_by_where_they_stopped(self):
        """
        어느 단계에서 무슨 오류가 났는지는 셀 수 있다.

        기록 한 벌 안에 둘 다 적혀 있기 때문이다 - 짝짓기가 아니다.
        """

        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  error="WorkspaceError")
        self.sent("을.json", beta_telemetry.WORKSPACE_SELECTED,
                  error="WorkspaceError")
        self.sent("병.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY, error="FileNotFoundError")

        rows = {row["key"]: row for row in self.now()["stages"]}

        self.assertEqual(
            rows[beta_dashboard.WORKSPACE_SELECTED]["errors"],
            [{"kind": "WorkspaceError", "count": 2}])
        self.assertEqual(
            rows[beta_dashboard.SCRIPT_READY]["errors"],
            [{"kind": "FileNotFoundError", "count": 1}])

    def test_a_stage_with_nothing_has_an_empty_list(self):
        rows = {row["key"]: row for row in self.now()["stages"]}

        self.assertEqual(rows[beta_dashboard.DONE]["errors"], [])
        self.assertEqual(rows[beta_dashboard.DONE]["stopped"], 0)


class FeedbackFileTest(Base):
    """2. 피드백 글은 세기만 한다."""

    def test_it_counts_the_files_only(self):
        self.wrote("2026-08-09 안 되던 것.txt", "또 하나.txt")

        found = self.now()

        self.assertEqual(found["feedback_files"], 2)

    def test_it_never_reads_the_names_or_the_contents(self):
        """
        이름도 내용도 담지 않는다.

        그 글에는 경로도 대본도 들어 있다 - 사람이 자유롭게 쓴
        것이기 때문이다.
        """

        self.wrote("무릎 영상 안 됨.txt")

        body = json.dumps(self.now(), ensure_ascii=False)

        for leak in ("무릎", "안 됨", ".txt", "C:\\", "사람", "내자료"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

    def test_no_folder_means_zero_not_an_error(self):
        found = self.now()

        self.assertEqual(found["feedback_files"], 0)

    def test_it_says_the_count_is_mine_only(self):
        """
        피드백 글은 내 PC의 것만 보인다.

        그것을 "베타 참가자 의견 n건"으로 읽으면 안 된다.
        """

        self.wrote("하나.txt")

        self.assertTrue(any("이 PC" in line
                            for line in self.now()["notes"]))


class HonestyTest(Base):
    """3. 없는 것을 지어내지 않는다."""

    def test_it_does_not_claim_opinions_per_stage(self):
        """
        '의견 3건'이라고 부르지 않는다.

        그렇게 부르면 누군가 그 셋을 읽으려 든다. 있는 것은 "그
        단계에서 멈춘 설치본 3벌"이다.
        """

        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED)

        found = self.now()

        # 단계 줄만 본다. notes에는 "의견 건수가 아닙니다"라고 적혀
        # 있어서, 전체를 훑으면 그 부정문이 걸린다 - 이 저장소가
        # 반복해 겪은 오탐이다.
        self.assertNotIn("의견",
                         json.dumps(found["stages"], ensure_ascii=False))

        self.assertTrue(any("의견" in line and "아닙니다" in line
                            for line in found["notes"]),
                        found["notes"])

    def test_it_never_says_why(self):
        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  error="WorkspaceError")

        body = json.dumps(self.now(), ensure_ascii=False)

        for claim in ("때문에 막혔", "원인은", "어렵기 때문"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, body)

    def test_it_reads_only_what_exists(self):
        import re

        source = os.path.join(REPO, "app", "services",
                              "beta_feedback_loop.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        self.assertIn("beta_dashboard", code)

        # 글을 여는 일이 없어야 한다 - 개수만 센다.
        for forbidden in ("open(", "json.load", "read(", "record(",
                          "launched(", "generate_", "makedirs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class QuietTest(Base):
    """4. 읽기만 한다."""

    def test_nothing_is_written(self):
        beta_telemetry.launched()
        self.wrote("하나.txt")

        before = sorted(os.listdir(self.home))

        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_new_event(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        before = json.dumps(beta_telemetry.events(), ensure_ascii=False)

        self.now()

        self.assertEqual(
            json.dumps(beta_telemetry.events(), ensure_ascii=False), before)

    def test_no_maker_is_called(self):
        from app.services import studio_jobs, studio_review

        with patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            self.now()

            render.assert_not_called()
            start.assert_not_called()


class ApiTest(Base):
    """5. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/beta-feedback-insights")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("stages", "feedback_files", "notes", "installations"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_screen_numbers_are_the_api_numbers(self):
        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED)

        found = self.client.get(
            "/studio/api/beta-feedback-insights").json()

        self.assertEqual([row["stopped"] for row in found["stages"]],
                         [row["stopped"] for row in
                          beta_feedback_loop.build()["stages"]])

    def test_the_screen_has_the_card(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-feedback-insights", page)
        self.assertIn("피드백 현황", page)
        self.assertIn("row.stopped", page)


if __name__ == "__main__":
    unittest.main()
