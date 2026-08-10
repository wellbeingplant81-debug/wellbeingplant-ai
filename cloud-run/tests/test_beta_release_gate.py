"""
Sprint199 - 배포 확인 정보를 한 장으로 (Epic 59, Phase 17).

Sprint191~198이 만든 자리들을 한 장에 모은다. 여기서 새로 세거나
판정하지 않는다.

이름이 Gate지만 문을 여닫지 않는다
----------------------------------
이 표는 "지금 확인된 것"과 "아직 모르는 것"을 늘어놓을 뿐이고, 문을
열지 말지는 사람이 정한다. 그래서 "배포 가능" 같은 말이 답에 없는지를
테스트가 직접 본다.

기록은 한 번만 읽는다
---------------------
Sprint190·192·193이 같은 원칙을 세 번 세웠다. 따로 읽으면 한 장 안에서
숫자가 어긋난다 - 설치본은 5벌인데 흐름은 6벌에서 센 것처럼.

Gate는 사슬의 마지막이라 여기서 어긋나면 앞의 셋이 지킨 것이 전부
무너진다. 그래서 beta_dashboard를 몇 번 읽었는지를 센다.

금지 문구는 긍정형만 본다
-------------------------
beta_readiness의 caution에는 "내보내도 된다는 뜻은 아닙니다"가 들어
있다. 부분 문자열로 찾으면 그 부정문에 걸려 거짓 판정이 난다.
"""

import ast
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

from app import app_info, runtime_paths
from app.routers import studio as studio_router
from app.services import (
    beta_dashboard, beta_readiness, beta_release_gate, beta_release_report,
    beta_snapshot, beta_summary, beta_telemetry,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 최종 판단을 뜻하는 말. 전부 긍정형이다 - caution의 부정문에 걸리지
# 않게 하려는 것이다.
NEVER_SAID = ("배포 가능", "출시 준비 완료", "안전함", "배포해도 됩니다")


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
                                   "timestamp": "2026-08-10T10:00:00",
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
        return beta_release_gate.build()


class ShapeTest(Base):
    """1. 무엇이 담기는가."""

    def test_it_carries_the_declared_fields(self):
        found = self.now()

        for key in ("taken_at", "version", "summary", "readiness",
                    "snapshot", "release", "diagnostic", "warnings", "note"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_summary_carries_what_was_asked(self):
        found = self.now()["summary"]

        for key in ("installations", "started", "finished", "success_rate",
                    "top_blocked_stage", "error_kinds", "next_action"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_release_carries_the_pasteable_text(self):
        found = self.now()["release"]

        for key in ("version", "checked_at", "funnel", "cautions", "report"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_diagnostic_line_is_the_readiness_one(self):
        found = self.now()

        self.assertEqual(found["diagnostic"]["key"], "diagnostic")
        self.assertIn(found["diagnostic"], found["readiness"]["checks"])


class SameNumbersTest(Base):
    """2. 앞의 자리들과 같은 말을 한다."""

    def test_the_summary_numbers_are_the_summary_numbers(self):
        self.some()

        found = self.now()["summary"]
        theirs = beta_summary.build()

        for key in ("installations", "started", "finished", "success_rate",
                    "top_blocked_stage", "error_kinds"):
            with self.subTest(key=key):
                self.assertEqual(found[key], theirs[key])

    def test_the_readiness_is_what_readiness_says(self):
        self.some()

        found = self.now()["readiness"]
        theirs = beta_readiness.build()

        self.assertEqual(found["checks"], theirs["checks"])
        self.assertEqual(found["passed"], theirs["passed"])
        self.assertEqual(found["failed"], theirs["failed"])
        self.assertEqual(found["unknown"], theirs["unknown"])

    def test_the_flow_is_the_release_report_funnel(self):
        self.some()

        found = self.now()["release"]["funnel"]
        theirs = beta_release_report.build()["funnel"]

        self.assertEqual([row["count"] for row in found],
                         [row["count"] for row in theirs])

    def test_one_moment_not_two(self):
        """
        확인 시점이 두 개면 어느 쪽이 맞는지 알 수 없다.
        """

        found = self.now()

        self.assertEqual(found["taken_at"], found["snapshot"]["taken_at"])
        self.assertEqual(found["taken_at"], found["release"]["checked_at"])

    def test_the_version_is_the_app_version(self):
        self.assertEqual(self.now()["version"], app_info.VERSION)


class ReadOnceTest(Base):
    """3. 기록을 한 번만 읽는다."""

    def test_the_record_is_read_once(self):
        """
        Gate는 사슬의 마지막이다. 여기서 두 번 읽으면 앞의 셋이 지킨
        것이 마지막 한 장에서 무너진다.
        """

        self.some()

        with patch.object(beta_dashboard, "build",
                          wraps=beta_dashboard.build) as counted:
            beta_release_gate.build()

            self.assertEqual(counted.call_count, 1)


class NoNewJudgementTest(Base):
    """4. 판정하지 않는다."""

    def test_it_never_says_it_is_ready(self):
        self.some()

        body = json.dumps(self.now(), ensure_ascii=False)

        for said in NEVER_SAID:
            with self.subTest(said=said):
                self.assertNotIn(said, body)

    def test_the_caution_is_carried_as_it_is(self):
        """
        "전부 O여도 내보내도 된다는 뜻은 아닙니다" - 그 말이 빠지면
        이 표는 안심시키는 그림이 된다.
        """

        found = self.now()

        self.assertEqual(found["readiness"]["caution"], beta_readiness.CAUTION)
        self.assertIn(beta_readiness.CAUTION, found["release"]["cautions"])

    def test_it_does_not_count_anything(self):
        """세는 코드가 있으면 그것이 곧 새 판정이다."""

        source = os.path.join(REPO, "app", "services",
                              "beta_release_gate.py")

        with open(source, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        counted = [node.func.id for node in ast.walk(tree)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id in ("sum", "len", "max", "min", "sorted")]

        self.assertEqual(counted, [])

    def test_it_asks_only_the_places_it_should(self):
        source = os.path.join(REPO, "app", "services",
                              "beta_release_gate.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = __import__("re").sub(r'"""[\s\S]*?"""', "", body)
        code = __import__("re").sub(r"(?m)#.*$", "", code)

        for wanted in ("beta_summary", "beta_snapshot", "beta_release_report"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        # diagnostic_report는 readiness가 이미 물어봤다. 다시 부르면
        # 그것이 두 번째 읽기가 되고 두 답이 어긋날 수 있다.
        for forbidden in ("diagnostic_report", "beta_dashboard",
                          "open(", "listdir", "makedirs", "record("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class NotSavedTest(Base):
    """5. 떠 두기만 하고 적지 않는다."""

    def test_nothing_is_written(self):
        self.some()

        before = sorted(os.listdir(self.home))

        self.now()
        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_new_event(self):
        self.some()

        before = json.dumps(beta_telemetry.events(), ensure_ascii=False)

        self.now()

        self.assertEqual(
            json.dumps(beta_telemetry.events(), ensure_ascii=False), before)

    def test_it_says_it_is_not_saved(self):
        found = self.now()

        self.assertIn("저장", found["note"])


class PrivacyTest(Base):
    """6. 남의 것이 들어가지 않는다."""

    def test_nothing_personal(self):
        self.some()

        folder = runtime_paths.ensure(runtime_paths.feedback_root())

        # 탐침으로 쓰는 낱말은 화면 글에 나올 법하지 않은 것이어야
        # 한다. 앞선 스프린트들은 "사람"을 썼는데, 이 표의 note가
        # "내보낼지는 사람이 정합니다"라고 말하므로 그 낱말로는 유출과
        # 제 글을 구별할 수 없다.
        with open(os.path.join(folder, "무릎 안 됨.txt"), "w",
                  encoding="utf-8") as f:
            f.write(r"C:\Users\홍길동\내자료 를 골랐습니다")

        body = json.dumps(self.now(), ensure_ascii=False)

        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME",
                     "무릎", "안 됨", "내자료", "홍길동"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))


class TheOldPlacesStillWorkTest(Base):
    """7. 앞의 자리들은 그대로다."""

    def test_a_snapshot_without_an_argument_is_unchanged(self):
        """
        주입구가 생겨도 인자를 주지 않으면 예전과 같아야 한다.
        """

        self.some()

        found = beta_snapshot.build()

        for key in ("taken_at", "version", "installations", "flow",
                    "readiness", "warnings", "note"):
            with self.subTest(key=key):
                self.assertIn(key, found)

        self.assertEqual([row["count"] for row in found["flow"]],
                         [row["count"] for row in
                          beta_summary.build()["funnel"]["steps"]])

    def test_a_snapshot_takes_the_summary_it_is_given(self):
        self.some()

        summary = beta_summary.build()

        with patch.object(beta_summary, "build") as never:
            found = beta_snapshot.build(summary)

            never.assert_not_called()

        self.assertEqual(found["installations"], summary["installations"])


class ApiTest(Base):
    """8. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/beta-release-gate")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("taken_at", "summary", "readiness", "release",
                    "diagnostic", "note"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        self.some()

        found = self.client.get("/studio/api/beta-release-gate").json()

        self.assertEqual(
            found["summary"]["installations"],
            beta_release_gate.build()["summary"]["installations"])

    def test_the_screen_has_the_button(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-release-gate", page)
        self.assertIn("배포 확인 정보", page)


if __name__ == "__main__":
    unittest.main()
