"""
Sprint185 - 어디를 먼저 고칠 것인가 (Epic 59, Phase 8).

Sprint184가 "어디에서 멈췄는가"를 세어 줬다. 그 숫자를 놓고 "그래서
무엇부터 고칠까"를 정하는 일은 아직 사람이 해야 했다.

숫자를 지어내지 않는다
----------------------
    기록이 없으면 없다고 한다
    아무도 없는 단계도 0으로 남긴다
    같은 수로 겹치면 하나를 고르지 않는다

특히 셋째가 중요하다. 두 벌짜리 기록에서 "가장 많이 막힌 곳"을
단정하면, 그것은 자료가 아니라 우연이다. 몇 벌을 보고 한 말인지도
함께 내준다.

세는 일은 여기서 하지 않는다
----------------------------
beta_dashboard가 낸 결과만 읽는다 - 두 자리가 각각 세면 화면마다
다른 숫자가 뜬다.
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
from app.services import beta_dashboard, beta_insights, beta_telemetry

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dashboard(blocked, **changed):
    """beta_dashboard가 내는 모양 그대로."""

    found = {
        "installations": sum(blocked.values()),
        "unreadable": 0,
        "users_started": sum(blocked.values()),
        "launch_count": sum(blocked.values()),
        "workspace_selected": 0,
        "script_ready": 0,
        "render_started": 0,
        "render_completed": blocked.get(beta_dashboard.DONE, 0),
        "render_failed": 0,
        "error_kinds": {},
        "blocked_stage": {stage: blocked.get(stage, 0)
                          for stage in beta_dashboard.STAGES},
        "collected_dirname": beta_dashboard.COLLECTED_DIRNAME,
    }

    found.update(changed)

    return found


class NoDataTest(unittest.TestCase):
    """1. 없는 것을 지어내지 않는다."""

    def test_nothing_yet_says_so(self):
        found = beta_insights.build(_dashboard({}))

        self.assertIsNone(found["top_blocked_stage"])
        self.assertEqual(found["installations"], 0)
        self.assertTrue(any("기록" in line
                            for line in found["recommendations"]))

    def test_zero_stages_stay(self):
        """
        아무도 없는 단계도 0으로 남긴다.

        줄이 사라지면 "그 단계가 없다"로 읽힌다.
        """

        found = beta_insights.build(
            _dashboard({beta_dashboard.SCRIPT_READY: 2}))

        for stage in beta_dashboard.STAGES:
            with self.subTest(stage=stage):
                self.assertIn(stage, found["stage_counts"])

        self.assertEqual(found["stage_counts"][beta_dashboard.DONE], 0)


class TopTest(unittest.TestCase):
    """2. 가장 많이 막힌 곳."""

    def test_a_clear_winner_is_named(self):
        found = beta_insights.build(_dashboard({
            beta_dashboard.WORKSPACE_SELECTED: 2,
            beta_dashboard.SCRIPT_READY: 5,
            beta_dashboard.DONE: 1,
        }))

        self.assertEqual(found["top_blocked_stage"],
                         beta_dashboard.SCRIPT_READY)
        self.assertFalse(found["tied"])
        self.assertEqual(found["installations"], 8)

    def test_a_tie_is_not_resolved_by_us(self):
        """
        같은 수로 겹치면 하나를 고르지 않는다.

        고르면 그것은 자료가 아니라 우리 취향이다.
        """

        found = beta_insights.build(_dashboard({
            beta_dashboard.WORKSPACE_SELECTED: 3,
            beta_dashboard.SCRIPT_READY: 3,
        }))

        self.assertIsNone(found["top_blocked_stage"])
        self.assertTrue(found["tied"])
        self.assertEqual(sorted(found["top_candidates"]),
                         sorted([beta_dashboard.WORKSPACE_SELECTED,
                                 beta_dashboard.SCRIPT_READY]))

    def test_finishing_is_not_a_blocked_stage(self):
        """
        끝까지 간 것이 가장 많아도 그것은 막힌 곳이 아니다.
        """

        found = beta_insights.build(_dashboard({
            beta_dashboard.DONE: 9,
            beta_dashboard.SCRIPT_READY: 1,
        }))

        self.assertEqual(found["top_blocked_stage"],
                         beta_dashboard.SCRIPT_READY)

    def test_everyone_finished_means_nothing_is_blocked(self):
        found = beta_insights.build(_dashboard({beta_dashboard.DONE: 4}))

        self.assertIsNone(found["top_blocked_stage"])
        self.assertFalse(found["tied"])
        self.assertTrue(any("끝까지" in line
                            for line in found["recommendations"]))

    def test_it_says_how_many_records_it_looked_at(self):
        """
        몇 벌을 보고 한 말인지 함께 낸다.

        두 벌짜리에서 "가장 많이 막힌 곳"을 단정하면 그것은 자료가
        아니라 우연이다.
        """

        found = beta_insights.build(_dashboard({
            beta_dashboard.SCRIPT_READY: 2}))

        self.assertEqual(found["installations"], 2)
        self.assertTrue(found["thin"])

        many = beta_insights.build(_dashboard({
            beta_dashboard.SCRIPT_READY: beta_insights.ENOUGH}))

        self.assertFalse(many["thin"])


class FailureTest(unittest.TestCase):
    """3. 자주 나는 오류."""

    def test_it_lists_what_was_recorded(self):
        found = beta_insights.build(_dashboard(
            {beta_dashboard.SCRIPT_READY: 3},
            error_kinds={"FileNotFoundError": 2, "WorkspaceError": 1}))

        self.assertEqual(found["common_failures"],
                         [{"kind": "FileNotFoundError", "count": 2},
                          {"kind": "WorkspaceError", "count": 1}])

    def test_no_errors_is_an_empty_list_not_a_guess(self):
        found = beta_insights.build(_dashboard(
            {beta_dashboard.SCRIPT_READY: 1}))

        self.assertEqual(found["common_failures"], [])


class RecommendationTest(unittest.TestCase):
    """4. 개선 후보."""

    def test_every_stage_has_something_to_look_at(self):
        for stage in beta_dashboard.STAGES:
            with self.subTest(stage=stage):
                self.assertIn(stage, beta_insights.WHERE_TO_LOOK)
                self.assertTrue(beta_insights.WHERE_TO_LOOK[stage])

    def test_the_top_stage_decides_what_to_look_at(self):
        found = beta_insights.build(_dashboard({
            beta_dashboard.SCRIPT_READY: 4,
            beta_dashboard.WORKSPACE_SELECTED: 1,
        }))

        self.assertTrue(any("대본" in line
                            for line in found["recommendations"]))

    def test_a_thin_sample_is_said_out_loud(self):
        found = beta_insights.build(_dashboard({
            beta_dashboard.SCRIPT_READY: 2}))

        self.assertTrue(any("적" in line
                            for line in found["recommendations"]),
                        found["recommendations"])

    def test_failures_are_mentioned_when_there_are_any(self):
        found = beta_insights.build(_dashboard(
            {beta_dashboard.SCRIPT_READY: 3},
            error_kinds={"FileNotFoundError": 5}))

        self.assertTrue(any("FileNotFoundError" in line
                            for line in found["recommendations"]))


class DashboardTest(unittest.TestCase):
    """5. dashboard가 실제로 그 모양을 낸다."""

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_the_dashboard_counts_error_kinds(self):
        """
        오류 종류를 세는 일은 dashboard가 한다.

        두 자리가 각각 세면 화면마다 다른 숫자가 뜬다.
        """

        beta_telemetry.launched()
        beta_telemetry.failed(FileNotFoundError("없다"))

        folder = runtime_paths.ensure(beta_dashboard.collected_root())

        with open(os.path.join(folder, "갑.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"version": 1, "launch_count": 1, "events": [],
                       "seen": [], "last_error_kind": "FileNotFoundError",
                       "last_error_time": "2026-08-09T10:00:00",
                       "first_launch_at": None, "last_launch_at": None}, f)

        found = beta_dashboard.build()

        self.assertEqual(found["error_kinds"]["FileNotFoundError"], 2)

    def test_insights_reads_the_real_dashboard(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        found = beta_insights.build()

        self.assertEqual(found["installations"], 1)
        self.assertEqual(found["top_blocked_stage"],
                         beta_dashboard.WORKSPACE_SELECTED)


class QuietTest(unittest.TestCase):
    """6. 읽기만 한다."""

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_nothing_personal(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        body = json.dumps(beta_insights.build(), ensure_ascii=False)

        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))

    def test_nothing_is_written(self):
        beta_telemetry.launched()

        before = sorted(os.listdir(self.home))

        beta_insights.build()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_it_counts_nothing_by_itself(self):
        import re

        source = os.path.join(REPO, "app", "services", "beta_insights.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        self.assertIn("beta_dashboard", code)

        for forbidden in ("open(", "listdir", "json.load", "generate_",
                          "makedirs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


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
        answer = self.client.get("/studio/api/beta-insights")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("top_blocked_stage", "stage_counts", "common_failures",
                    "recommendations"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.SCRIPT_READY)

        self.assertEqual(
            self.client.get("/studio/api/beta-insights").json()
            ["top_blocked_stage"],
            beta_insights.build()["top_blocked_stage"])

    def test_the_screen_has_the_card(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-insights", page)
        self.assertIn("베타 분석", page)
        self.assertIn("개선 후보", page)


if __name__ == "__main__":
    unittest.main()
