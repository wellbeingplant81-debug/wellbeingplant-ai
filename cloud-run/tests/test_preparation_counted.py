"""
Sprint206 - 적히는데 아무도 안 세는 걸음 (Epic 59, Phase 21).

beta_telemetry가 아는 사건은 여섯인데 세는 쪽은 다섯만 안다.

    workspace_selected · script_ready · preparation_ready
    render_started · render_completed · render_failed

preparation_ready는 실제로 적힌다(studio.py:1950, 프로젝트당 한 번).
그런데 ORDER에도 STAGES에도 COUNTED에도 없다 - 모든 사용자의 기록에
들어 있는데 아무도 읽지 않는 숫자다.

그래서 둘이 같은 칸에 들어간다
------------------------------
    갑  대본 넣고 그만둠                    script_ready 에서 멈춤
    을  자료까지 갖추고 제작 직전에 그만둠  script_ready 에서 멈춤

자료를 못 모아서 못 간 사람과, 다 모아 놓고 안 누른 사람을 구별할 수
없다. 고칠 곳이 전혀 다른데도.

세기만 한다
-----------
ORDER와 STAGES는 건드리지 않는다. 넣으면 blocked_stage 바구니가
달라지고, 어제까지 script_ready로 세어지던 사람이 오늘부터 다른 칸으로
옮겨간다 - 그것은 이미 내려진 판정을 바꾸는 일이다.

숫자가 생겼다고 판정이 생긴 것도 아니다. "몇 벌이 거기까지 갔다"와
"그것으로 충분한가"는 다른 말이고, 후자를 판정하는 자리는 여전히 없다.
그래서 RC 카드의 그 줄은 수를 얻어도 ok는 ? 그대로다.
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
from app.services import (
    beta_dashboard, beta_funnel, beta_release_candidate, beta_summary,
    beta_telemetry,
)

ASSETS = "assets"


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        self.store = os.path.join(self.home, "workspace.json")

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

    def two_got_their_assets(self):
        """자료까지 갖춘 기록 둘, 대본까지만 간 기록 하나."""

        beta_telemetry.launched()

        self.sent("갑.json",
                  beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)
        self.sent("을.json",
                  beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.PREPARATION_READY)
        self.sent("병.json",
                  beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.PREPARATION_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_COMPLETED)


class ItIsCountedTest(Base):
    """1. 이미 적혀 있는 것을 센다."""

    def test_the_dashboard_counts_it(self):
        self.two_got_their_assets()

        self.assertIn(beta_telemetry.PREPARATION_READY,
                      beta_dashboard.build())

    def test_the_count_is_what_the_records_say(self):
        self.two_got_their_assets()

        self.assertEqual(
            beta_dashboard.build()[beta_telemetry.PREPARATION_READY], 2)

    def test_it_is_in_the_counted_list(self):
        self.assertIn(beta_telemetry.PREPARATION_READY,
                      beta_dashboard.COUNTED)


class TheCardShowsItTest(Base):
    """2. Sprint200이 비워 둔 자리를 채운다."""

    def step(self, key):
        found = beta_release_candidate.build(self.store, None)

        for row in found["journey"]:
            if row["key"] == key:
                return row

        raise AssertionError(f"걸음이 없습니다: {key}")

    def test_the_assets_step_has_a_number_now(self):
        self.two_got_their_assets()

        self.assertEqual(self.step(ASSETS)["count"], 2)

    def test_a_number_is_not_a_verdict(self):
        """
        "몇 벌이 거기까지 갔다"와 "그것으로 충분한가"는 다른 말이다.
        """

        self.two_got_their_assets()

        self.assertIsNone(self.step(ASSETS)["ok"])

    def test_it_says_nobody_judges_it(self):
        self.two_got_their_assets()

        said = self.step(ASSETS)["detail"]

        self.assertIn("판정", said)


class NothingElseMovedTest(Base):
    """3. 판정하는 자리는 그대로다."""

    def test_the_buckets_are_still_five(self):
        self.assertEqual(len(beta_dashboard.STAGES), 5)
        self.assertNotIn(beta_telemetry.PREPARATION_READY,
                         beta_dashboard.STAGES)

    def test_the_order_is_untouched(self):
        self.assertNotIn(beta_telemetry.PREPARATION_READY,
                         beta_dashboard.ORDER)

    def test_the_funnel_still_has_five_steps(self):
        self.assertEqual(len(beta_funnel.STEPS), 5)

    def test_where_people_stopped_is_unchanged(self):
        """
        갑과 을은 여전히 같은 칸에 있다. 이번에 그것을 바꾸지 않았다.
        """

        self.two_got_their_assets()

        blocked = beta_dashboard.build()["blocked_stage"]

        self.assertEqual(blocked[beta_dashboard.SCRIPT_READY], 2)
        self.assertNotIn(beta_telemetry.PREPARATION_READY, blocked)

    def test_the_success_rate_is_unchanged(self):
        self.two_got_their_assets()

        summary = beta_summary.build()

        self.assertEqual(summary["finished"], 1)
        self.assertEqual(summary["started"], 4)

    def test_no_new_event_name(self):
        """
        세는 쪽만 고친다. 적는 쪽에 이름이 하나라도 늘면 그것은 새
        기록 수집이다.
        """

        self.assertEqual(beta_telemetry.EVENTS, (
            "workspace_selected",
            "script_ready",
            "preparation_ready",
            "render_started",
            "render_completed",
            "render_failed",
            "output_check_failed",
        ))


class LeavesNothingTest(Base):
    """4. 세느라 무엇을 만들지 않는다."""

    def test_nothing_is_written(self):
        self.two_got_their_assets()

        before = sorted(os.listdir(self.home))

        beta_dashboard.build()
        beta_release_candidate.build(self.store, None)

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_new_record(self):
        self.two_got_their_assets()

        before = json.dumps(beta_telemetry.events(), ensure_ascii=False)

        beta_dashboard.build()

        self.assertEqual(
            json.dumps(beta_telemetry.events(), ensure_ascii=False), before)

    def test_nothing_personal(self):
        self.two_got_their_assets()

        body = json.dumps(beta_release_candidate.build(self.store, None),
                          ensure_ascii=False)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))
        self.assertNotIn(os.environ.get("USERNAME") or "USERNAME", body)


if __name__ == "__main__":
    unittest.main()
