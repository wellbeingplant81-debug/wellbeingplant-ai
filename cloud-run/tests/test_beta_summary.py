"""
Sprint190 - 베타 운영 정보를 한 장으로 (Epic 59, Phase 13).

Sprint184부터 다섯 자리가 각각 제 이야기를 하게 됐다. 보려면 다섯
번 눌러야 했고, 누를 때마다 기록을 다시 읽었다.

한 번만 읽는다
--------------
다섯이 각각 기록을 읽으면 그 사이에 파일이 바뀔 수 있다. 그러면 한
화면 안에서 숫자가 서로 어긋난다 - 설치본은 5벌인데 흐름은 6벌에서
센 것처럼.

그래서 beta_dashboard를 한 번 읽고, 그 하나를 다섯에게 나눠 준다.

새로 세지 않는다
----------------
여기서 더하거나 고르는 것이 없다. 다섯이 낸 답을 그대로 담고, 화면이
자주 보는 것만 위로 꺼내 놓는다.
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
    beta_action_tracking, beta_actions, beta_dashboard, beta_feedback_loop,
    beta_funnel, beta_insights, beta_summary, beta_telemetry,
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

    def sent(self, name, *events, kind=None, launches=1):
        folder = runtime_paths.ensure(beta_dashboard.collected_root())

        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "launch_count": launches,
                       "first_launch_at": None, "last_launch_at": None,
                       "events": [{"event": e,
                                   "timestamp": "2026-08-09T10:00:00",
                                   "version": "0.1.0"} for e in events],
                       "seen": [], "last_error_kind": kind,
                       "last_error_time": None}, f, ensure_ascii=False)

    def some(self):
        """볼 만한 기록 몇 벌."""

        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  kind="WorkspaceError")
        self.sent("을.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)
        self.sent("병.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_COMPLETED)

    def now(self):
        return beta_summary.build()


class AgreementTest(Base):
    """1. 다섯이 낸 답과 같은 말을 한다."""

    def test_each_part_is_what_its_own_service_says(self):
        """
        여기서 다시 세지 않는다.

        다시 세면 한 화면 안에서 숫자가 서로 어긋난다.
        """

        self.some()

        found = self.now()
        dashboard = beta_dashboard.build()

        self.assertEqual(found["dashboard"], dashboard)
        self.assertEqual(found["insights"],
                         beta_insights.build(dashboard))
        self.assertEqual(found["funnel"], beta_funnel.build(dashboard))
        self.assertEqual(found["feedback"],
                         beta_feedback_loop.build(dashboard))

    def test_the_action_parts_come_from_the_same_insights(self):
        self.some()

        found = self.now()
        insights = beta_insights.build(beta_dashboard.build())
        card = beta_actions.build(insights)

        self.assertEqual(found["action"], card)
        self.assertEqual(found["progress"],
                         beta_action_tracking.build(card))

    def test_everyone_saw_the_same_snapshot(self):
        """
        다섯이 같은 한 벌을 보고 말한다.

        각자 읽으면 그 사이에 파일이 바뀔 수 있고, 그러면 설치본은
        5벌인데 흐름은 6벌에서 센 것처럼 어긋난다.
        """

        self.some()

        found = self.now()

        counted = found["dashboard"]["installations"]

        self.assertEqual(found["insights"]["installations"], counted)
        self.assertEqual(found["funnel"]["started"], counted)
        self.assertEqual(found["feedback"]["installations"], counted)

    def test_it_reads_the_record_once(self):
        """
        기록 파일을 한 번만 읽는다.

        다섯이 각자 읽으면 다섯 번 열리고, 그 사이가 벌어진다.
        """

        self.some()

        with patch.object(beta_dashboard, "build",
                          wraps=beta_dashboard.build) as counted:
            beta_summary.build()

            self.assertEqual(counted.call_count, 1)


class HeadlineTest(Base):
    """2. 화면이 자주 보는 것."""

    def test_the_numbers_are_pulled_up(self):
        self.some()

        found = self.now()

        self.assertEqual(found["installations"],
                         found["dashboard"]["installations"])
        self.assertEqual(found["started"], found["funnel"]["started"])
        self.assertEqual(found["finished"], found["funnel"]["finished"])
        self.assertEqual(found["top_blocked_stage"],
                         found["insights"]["top_blocked_stage"])

    def test_the_error_kinds_come_from_the_dashboard(self):
        self.some()

        found = self.now()

        self.assertEqual(found["error_kinds"],
                         found["insights"]["common_failures"])

    def test_the_next_action_is_the_one_we_already_point_at(self):
        self.some()

        found = self.now()

        self.assertEqual(found["next_action"], found["action"]["action"])

    def test_nothing_yet_says_so_without_guessing(self):
        found = self.now()

        self.assertEqual(found["installations"], 0)
        self.assertIsNone(found["top_blocked_stage"])
        self.assertIsNone(found["next_action"])
        self.assertTrue(found["notes"])


class QuietTest(Base):
    """3. 읽기만 한다."""

    def test_nothing_is_written(self):
        self.some()

        before = sorted(os.listdir(self.home))

        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_new_event(self):
        self.some()

        before = json.dumps(beta_telemetry.events(), ensure_ascii=False)

        self.now()

        self.assertEqual(
            json.dumps(beta_telemetry.events(), ensure_ascii=False), before)

    def test_no_maker_is_called(self):
        from app.services import studio_jobs, studio_review

        self.some()

        with patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            self.now()

            render.assert_not_called()
            start.assert_not_called()

    def test_it_adds_nothing_of_its_own(self):
        import re

        source = os.path.join(REPO, "app", "services", "beta_summary.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for wanted in ("beta_dashboard", "beta_insights", "beta_funnel",
                       "beta_feedback_loop", "beta_action_tracking"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        for forbidden in ("open(", "listdir", "json.load", "record(",
                          "launched(", "generate_", "makedirs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class PrivacyTest(Base):
    """4. 남의 것이 들어가지 않는다."""

    def test_nothing_personal(self):
        self.some()

        folder = runtime_paths.ensure(runtime_paths.feedback_root())

        with open(os.path.join(folder, "무릎 안 됨.txt"), "w",
                  encoding="utf-8") as f:
            f.write(r"C:\Users\사람\내자료 를 골랐습니다")

        body = json.dumps(self.now(), ensure_ascii=False)

        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME",
                     "무릎", "안 됨", "내자료", "사람"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))

    def test_it_never_says_why(self):
        self.some()

        body = json.dumps(self.now(), ensure_ascii=False)

        for claim in ("때문에 막혔", "원인은", "어렵기 때문"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, body)


class ApiTest(Base):
    """5. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/beta-summary")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("installations", "started", "finished",
                    "top_blocked_stage", "next_action", "error_kinds",
                    "funnel", "notes"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        self.some()

        found = self.client.get("/studio/api/beta-summary").json()

        self.assertEqual(found["installations"],
                         beta_summary.build()["installations"])

    def test_the_screen_has_the_card(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-summary", page)
        self.assertIn("Beta Summary", page)


if __name__ == "__main__":
    unittest.main()
