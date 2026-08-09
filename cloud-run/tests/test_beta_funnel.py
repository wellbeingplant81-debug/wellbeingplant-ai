"""
Sprint188 - 전체 흐름을 한 줄로 (Epic 59, Phase 11).

Sprint184가 단계마다 세어 줬고 Sprint185가 어디가 가장 막히는지
골라 줬다. 그런데 "몇 명이 시작해서 몇 명이 끝냈는가"를 한눈에 보는
자리는 아직 없었다.

세지 않는다. 이미 센 것을 늘어놓는다
------------------------------------
beta_dashboard가 낸 숫자만 쓴다 - 두 자리가 각각 세면 화면마다 다른
숫자가 뜬다.

깔때기 모양을 억지로 만들지 않는다
----------------------------------
사건은 칸마다 따로 적힌다. 그래서 뒤 칸이 앞 칸보다 클 수 있다 -
Sprint184 실측에 render_started 없이 render_completed만 있는 기록이
실제로 있었다.

그때 숫자를 다듬어 매끈한 깔때기로 만들면 그것은 자료가 아니라
그림이다. 그대로 두고, 그런 칸이 있다고 말한다.

원인을 말하지 않는다
--------------------
"대본에서 많이 빠집니다"까지가 이 자리의 몫이고, "왜"는 여기서
말하지 않는다.
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
from app.services import beta_dashboard, beta_funnel, beta_telemetry

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dashboard(**counts):
    found = {
        "installations": 0, "unreadable": 0, "users_started": 0,
        "launch_count": 0, "workspace_selected": 0, "script_ready": 0,
        "render_started": 0, "render_completed": 0, "render_failed": 0,
        "error_kinds": {},
        "blocked_stage": {stage: 0 for stage in beta_dashboard.STAGES},
        "collected_dirname": beta_dashboard.COLLECTED_DIRNAME,
    }

    found.update(counts)

    return found


class ShapeTest(unittest.TestCase):
    """1. 다섯 칸."""

    def test_the_steps_are_the_declared_ones(self):
        found = beta_funnel.build(_dashboard())

        self.assertEqual([row["label"] for row in found["steps"]],
                         ["시작", "자료 연결", "대본 준비", "제작 시작",
                          "렌더 완료"])

    def test_every_row_carries_what_the_screen_draws(self):
        found = beta_funnel.build(_dashboard(
            installations=5, workspace_selected=5, script_ready=3,
            render_started=2, render_completed=1))

        for row in found["steps"]:
            with self.subTest(row=row["key"]):
                self.assertEqual(sorted(row),
                                 ["count", "dropped", "key", "label",
                                  "share"])

    def test_the_counts_come_from_the_dashboard(self):
        found = beta_funnel.build(_dashboard(
            installations=5, workspace_selected=5, script_ready=3,
            render_started=2, render_completed=1))

        self.assertEqual([row["count"] for row in found["steps"]],
                         [5, 5, 3, 2, 1])


class ArithmeticTest(unittest.TestCase):
    """2. 셈만 한다."""

    def test_the_drop_between_steps_is_plain_subtraction(self):
        found = beta_funnel.build(_dashboard(
            installations=5, workspace_selected=5, script_ready=3,
            render_started=2, render_completed=1))

        self.assertEqual([row["dropped"] for row in found["steps"]],
                         [0, 0, 2, 1, 1])

    def test_the_success_rate_is_finished_over_started(self):
        found = beta_funnel.build(_dashboard(
            installations=4, render_completed=1))

        self.assertEqual(found["success_rate"], 0.25)

    def test_no_one_started_means_no_rate(self):
        """
        나눌 것이 없으면 0이라고 하지 않는다.

        0%는 "아무도 못 끝냈다"는 뜻이고, 그것은 사실이 아니다 -
        아직 아무도 시작하지 않았을 뿐이다.
        """

        found = beta_funnel.build(_dashboard())

        self.assertIsNone(found["success_rate"])

    def test_the_share_is_of_the_first_step(self):
        found = beta_funnel.build(_dashboard(
            installations=4, workspace_selected=2))

        shares = {row["key"]: row["share"] for row in found["steps"]}

        self.assertEqual(shares["start"], 1.0)
        self.assertEqual(shares[beta_dashboard.WORKSPACE_SELECTED], 0.5)


class IrregularTest(unittest.TestCase):
    """3. 매끈하게 다듬지 않는다."""

    def test_a_later_step_bigger_than_an_earlier_one_is_shown_as_is(self):
        """
        뒤 칸이 앞 칸보다 커도 숫자를 고치지 않는다.

        Sprint184 실측에 render_started 없이 render_completed만 있는
        기록이 있었다. 다듬으면 그것은 자료가 아니라 그림이다.
        """

        found = beta_funnel.build(_dashboard(
            installations=3, workspace_selected=3, script_ready=3,
            render_started=0, render_completed=2))

        counts = {row["key"]: row["count"] for row in found["steps"]}

        self.assertEqual(counts[beta_dashboard.RENDER_STARTED], 0)
        self.assertEqual(counts[beta_telemetry.RENDER_COMPLETED], 2)

        self.assertTrue(found["irregular"])
        self.assertTrue(any("앞" in line for line in found["notes"]))

    def test_a_normal_funnel_says_nothing_odd(self):
        found = beta_funnel.build(_dashboard(
            installations=5, workspace_selected=5, script_ready=3,
            render_started=2, render_completed=1))

        self.assertFalse(found["irregular"])


class ThinTest(unittest.TestCase):
    """4. 부족하면 부족하다고 한다."""

    def test_no_data_says_so(self):
        found = beta_funnel.build(_dashboard())

        self.assertTrue(found["empty"])
        self.assertTrue(any("기록" in line for line in found["notes"]))

    def test_a_small_sample_is_said_out_loud(self):
        found = beta_funnel.build(_dashboard(installations=2))

        self.assertTrue(found["thin"])
        self.assertTrue(any("적" in line for line in found["notes"]))

    def test_enough_is_the_one_insights_uses(self):
        """
        "적다"의 기준을 여기서 새로 정하지 않는다.

        두 화면이 다른 기준으로 "적다"고 하면 사람이 헷갈린다.
        """

        from app.services import beta_insights

        self.assertEqual(beta_funnel.ENOUGH, beta_insights.ENOUGH)


class NoCauseTest(unittest.TestCase):
    """5. 원인을 말하지 않는다."""

    def test_it_never_explains_why(self):
        found = beta_funnel.build(_dashboard(
            installations=5, workspace_selected=5, script_ready=1))

        body = json.dumps(found, ensure_ascii=False)

        for wrong in ("때문", "원인", "어렵", "불편"):
            with self.subTest(wrong=wrong):
                self.assertNotIn(wrong, body)

    def test_it_counts_nothing_by_itself(self):
        import re

        source = os.path.join(REPO, "app", "services", "beta_funnel.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        self.assertIn("beta_dashboard", code)

        for forbidden in ("open(", "listdir", "json.load", "record(",
                          "launched(", "generate_", "makedirs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class LiveTest(unittest.TestCase):
    """6. 실제 기록에서."""

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_it_reads_the_real_dashboard(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)
        beta_telemetry.record(beta_telemetry.SCRIPT_READY)

        found = beta_funnel.build()
        counts = {row["key"]: row["count"] for row in found["steps"]}

        self.assertEqual(counts["start"], 1)
        self.assertEqual(counts[beta_dashboard.SCRIPT_READY], 1)
        self.assertEqual(counts[beta_telemetry.RENDER_COMPLETED], 0)

    def test_nothing_personal(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        body = json.dumps(beta_funnel.build(), ensure_ascii=False)

        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))

    def test_nothing_is_written(self):
        beta_telemetry.launched()

        before = sorted(os.listdir(self.home))

        beta_funnel.build()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_new_event_is_recorded(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        before = json.dumps(beta_telemetry.events(), ensure_ascii=False)

        beta_funnel.build()

        self.assertEqual(
            json.dumps(beta_telemetry.events(), ensure_ascii=False), before)


class ApiTest(unittest.TestCase):
    """7. 서버와 화면."""

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

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/beta-funnel")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("steps", "success_rate", "notes", "irregular", "thin"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_screen_numbers_are_the_api_numbers(self):
        """
        화면이 다시 세지 않는다.

        서버가 준 count를 그대로 그린다 - 다시 세면 두 숫자가 어느 날
        어긋난다.
        """

        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        found = self.client.get("/studio/api/beta-funnel").json()

        self.assertEqual([row["count"] for row in found["steps"]],
                         [row["count"] for row in
                          beta_funnel.build()["steps"]])

    def test_the_screen_has_the_card(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-funnel", page)
        self.assertIn("전체 흐름", page)
        self.assertIn("row.count", page)


if __name__ == "__main__":
    unittest.main()
