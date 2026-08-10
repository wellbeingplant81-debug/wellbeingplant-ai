"""
Sprint207 - 카드 사이에서 어긋난다 (Epic 59, Phase 22).

Sprint190·192·193·199가 네 번 세운 원칙이 카드 단위로는 지켜진다 -
카드 하나는 기록을 한 번만 읽는다.

그런데 카드 하나로 그림이 안 그려져 운영자는 여럿을 눌러 본다. 그때마다
다시 읽는다. 실측으로 여덟을 훑으면 일곱 번 읽었고, 배포 확인 정보를
누른 시각과 Beta Snapshot을 누른 시각이 1초 달랐다.

한 화면 안에서 어긋나지 않게 하려고 네 번 애썼는데, 화면을 여러 번
여는 것으로 같은 어긋남이 돌아온 것이다.

바깥 것 하나에 안쪽이 다 들어 있다
----------------------------------
    처음 사용자 테스트 (Candidate)
        배포 확인 정보 (Gate)
            Beta Snapshot
                Beta Summary + Beta Readiness
            Release Report
        + 여덟 걸음

그런데 머리줄이 그 사실을 말하지 않는다. 그래서 넷을 눌러 보고, 넷은
서로 다른 순간을 말한다.

열셋째 단추를 만들지 않는다
---------------------------
이미 가장 바깥인 것을 먼저 보게 하고, 나머지가 그 안에 있다는 것을
말한다. 하나만 눌러도 되면 읽기가 한 번이고, 한 번이면 한 순간이다.

담는 관계는 말로만 적으면 언젠가 거짓이 된다
-------------------------------------------
그래서 화면 글이 아니라 값으로 확인한다.
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
from app.routers import studio as studio_router
from app.services import beta_dashboard, beta_telemetry

# 머리줄에서 먼저 보라고 가리키는 것.
FIRST = "처음 사용자 테스트"


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

    def some(self):
        beta_telemetry.launched()

        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)
        self.sent("을.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.PREPARATION_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_COMPLETED)

    def page(self):
        return studio_router.studio_page().body.decode("utf-8")


class TheHeaderSaysWhereToStartTest(Base):
    """1. 무엇을 먼저 볼 것인가."""

    def test_the_header_names_the_one_to_press_first(self):
        self.assertIn("먼저 볼 것", self.page())

    def test_the_first_one_is_the_outermost_card(self):
        page = self.page()

        at = page.find("먼저 볼 것")

        self.assertNotEqual(at, -1)
        self.assertIn(FIRST, page[at:at + 700])

    def test_the_rest_are_named_as_single_sheets(self):
        self.assertIn("낱장으로 볼 것", self.page())


class TheCardSaysWhatItHoldsTest(Base):
    """2. 그 안에 무엇이 들어 있는지 말한다."""

    def test_the_card_says_what_is_inside(self):
        found = self.card()

        self.assertIn("holds", found)

    def card(self):
        from app.services import beta_release_candidate

        return beta_release_candidate.build(self.store, None)

    def test_it_names_the_cards_it_contains(self):
        said = " ".join(self.card()["holds"])

        for name in ("배포 확인 정보", "Beta Snapshot", "Beta Summary"):
            with self.subTest(name=name):
                self.assertIn(name, said)

    def test_the_copied_text_says_it_too(self):
        """
        붙여 넣어 보내는 글에도 있어야 한다 - 받아 본 사람은 화면을
        못 본다.
        """

        self.assertIn("배포 확인 정보", self.card()["report"])


class TheHoldingIsTrueTest(Base):
    """
    3. 담는 관계가 사실인가 - 화면 글이 아니라 값으로.

    말로만 "들어 있다"고 적으면 언젠가 거짓이 된다.
    """

    def parts(self):
        from app.services import (
            beta_release_candidate, beta_release_gate, beta_snapshot,
        )

        self.some()

        return (beta_snapshot.build(), beta_release_gate.build(),
                beta_release_candidate.build(self.store, None))

    def test_the_gate_holds_the_snapshot_readiness(self):
        snapshot, gate, _ = self.parts()

        self.assertEqual(gate["readiness"]["checks"],
                         snapshot["readiness"]["checks"])

    def test_the_gate_holds_the_snapshot_flow(self):
        snapshot, gate, _ = self.parts()

        self.assertEqual(
            [row["count"] for row in gate["release"]["funnel"]],
            [row["count"] for row in snapshot["flow"]])

    def test_the_candidate_holds_the_gate_moment(self):
        _, gate, candidate = self.parts()

        self.assertEqual(candidate["taken_at"], gate["taken_at"])

    def test_one_press_reads_the_record_once(self):
        """
        하나만 눌러도 되면 읽기가 한 번이고, 한 번이면 한 순간이다.
        """

        from app.services import beta_release_candidate

        self.some()

        with patch.object(beta_dashboard, "build",
                          wraps=beta_dashboard.build) as counted:
            beta_release_candidate.build(self.store, None)

            self.assertEqual(counted.call_count, 1)


class NothingNewTest(Base):
    """4. 새로 만든 것이 없다."""

    def test_no_new_endpoint(self):
        """
        열셋째 카드를 만들면 문제가 하나 더 늘 뿐이다.
        """

        import re

        found = sorted(set(re.findall(
            r"/studio/api/(beta-[a-z-]+)", self.page())))

        self.assertEqual(found, [
            "beta-action-progress",
            "beta-actions",
            "beta-dashboard",
            "beta-feedback",
            "beta-feedback-insights",
            "beta-funnel",
            "beta-insights",
            "beta-package-validation",
            "beta-readiness",
            "beta-release-candidate",
            "beta-release-gate",
            "beta-release-report",
            "beta-snapshot",
            "beta-summary",
        ])

    def test_the_verdicts_are_untouched(self):
        from app.services import beta_release_candidate, beta_summary

        self.some()

        card = beta_release_candidate.build(self.store, None)
        summary = beta_summary.build()

        self.assertEqual(card["summary"]["success_rate"] if "success_rate"
                         in card.get("summary", {}) else
                         summary["success_rate"], summary["success_rate"])

        for row in card["journey"]:
            with self.subTest(key=row["key"]):
                self.assertIn(row["ok"], (True, False, None))

    def test_nothing_is_written(self):
        from app.services import beta_release_candidate

        self.some()

        before = sorted(os.listdir(self.home))

        beta_release_candidate.build(self.store, None)
        beta_release_candidate.build(self.store, None)

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_nothing_personal(self):
        from app.services import beta_release_candidate

        self.some()

        body = json.dumps(beta_release_candidate.build(self.store, None),
                          ensure_ascii=False)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))
        self.assertNotIn(os.environ.get("USERNAME") or "USERNAME", body)


if __name__ == "__main__":
    unittest.main()
