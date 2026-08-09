"""
Sprint192 - 지금을 한 장으로 떠 둔다 (Epic 59, Phase 15).

Beta Summary와 Beta Readiness가 각각 지금을 말한다. 그런데 그 둘을
따로 부르면 사이가 벌어질 수 있고, "이때 확인했다"는 시각도 없다.

한 번 읽고 셋에게 나눠 준다
---------------------------
Sprint190에서 정한 그 규칙을 여기서도 지킨다. 따로 읽으면 한 장
안에서 숫자가 서로 어긋난다.

떠 두기만 하고 적지는 않는다
----------------------------
'스냅샷'이라는 말은 파일로 남긴다는 뜻으로 읽히기 쉽다. 여기서는
남기지 않는다 - 남기면 그것이 또 어디에 쌓이는지, 언제 지워지는지를
설명해야 한다. 그 사실을 payload가 직접 말한다.

다시 판정하지 않는다
--------------------
O/X/? 도 흐름의 숫자도 앞의 두 자리가 낸 그대로다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app_info, runtime_paths
from app.routers import studio as studio_router
from app.services import (
    beta_dashboard, beta_readiness, beta_snapshot, beta_summary,
    beta_telemetry,
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

    def sent(self, name, *events):
        folder = runtime_paths.ensure(beta_dashboard.collected_root())

        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "launch_count": 1,
                       "first_launch_at": None, "last_launch_at": None,
                       "events": [{"event": e,
                                   "timestamp": "2026-08-09T10:00:00",
                                   "version": "0.1.0"} for e in events],
                       "seen": [], "last_error_kind": None,
                       "last_error_time": None}, f, ensure_ascii=False)

    def some(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)
        self.sent("을.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_COMPLETED)

    def now(self):
        return beta_snapshot.build()


class ShapeTest(Base):
    """1. 무엇이 담기는가."""

    def test_it_carries_the_declared_fields(self):
        found = self.now()

        for key in ("taken_at", "version", "readiness", "flow",
                    "warnings", "note"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_it_says_when_it_was_taken(self):
        found = self.now()

        self.assertTrue(found["taken_at"])
        self.assertEqual(found["version"], app_info.VERSION)

    def test_the_flow_is_the_five_steps(self):
        found = self.now()

        self.assertEqual([row["label"] for row in found["flow"]],
                         ["시작", "자료 연결", "대본 준비", "제작 시작",
                          "렌더 완료"])


class AgreementTest(Base):
    """2. 앞의 두 자리와 같은 말을 한다."""

    def test_the_readiness_is_what_readiness_says(self):
        self.some()

        found = self.now()
        theirs = beta_readiness.build()

        self.assertEqual(found["readiness"]["checks"], theirs["checks"])
        self.assertEqual(found["readiness"]["passed"], theirs["passed"])
        self.assertEqual(found["readiness"]["failed"], theirs["failed"])
        self.assertEqual(found["readiness"]["unknown"], theirs["unknown"])

    def test_the_flow_is_what_the_funnel_says(self):
        self.some()

        found = self.now()
        theirs = beta_summary.build()["funnel"]

        self.assertEqual([row["count"] for row in found["flow"]],
                         [row["count"] for row in theirs["steps"]])

    def test_everyone_saw_the_same_snapshot(self):
        """
        따로 읽으면 한 장 안에서 숫자가 서로 어긋난다.
        """

        self.some()

        with patch.object(beta_dashboard, "build",
                          wraps=beta_dashboard.build) as counted:
            beta_snapshot.build()

            self.assertEqual(counted.call_count, 1)

    def test_it_judges_nothing_by_itself(self):
        import re

        source = os.path.join(REPO, "app", "services", "beta_snapshot.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for wanted in ("beta_summary", "beta_readiness"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        for forbidden in ("open(", "listdir", "json.load", "record(",
                          "launched(", "atomic_write", "makedirs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class NotSavedTest(Base):
    """3. 떠 두기만 하고 적지 않는다."""

    def test_nothing_is_written(self):
        self.some()

        before = sorted(os.listdir(self.home))

        self.now()
        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_it_says_it_is_not_saved(self):
        """
        '스냅샷'은 파일로 남긴다는 뜻으로 읽히기 쉽다.

        남기지 않는다는 사실을 payload가 직접 말한다 - 안 그러면
        사람이 나중에 그 파일을 찾는다.
        """

        found = self.now()

        self.assertIn("저장", found["note"])
        self.assertIn("않", found["note"])

    def test_no_new_event(self):
        self.some()

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

        for claim in ("때문에 막혔", "원인은", "배포해도 됩니다"):
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
        answer = self.client.get("/studio/api/beta-snapshot")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("taken_at", "readiness", "flow", "warnings", "note"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        self.some()

        found = self.client.get("/studio/api/beta-snapshot").json()

        self.assertEqual([row["count"] for row in found["flow"]],
                         [row["count"] for row in
                          beta_snapshot.build()["flow"]])

    def test_the_screen_has_the_card(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-snapshot", page)
        self.assertIn("Beta Snapshot", page)
        self.assertIn("확인 시점", page)


if __name__ == "__main__":
    unittest.main()
