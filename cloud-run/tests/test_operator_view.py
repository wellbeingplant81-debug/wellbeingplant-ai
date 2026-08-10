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


class BeforeHandingItOutTest(Base):
    """
    Sprint208 - 나눠 주기 전에 확인할 것.

    베타를 시작하는 사람에게는 두 가지가 한 질문이다 - "지금 이걸
    남에게 줘도 되는가". 그런데 나눠 줄 물건(디스크)과 받을 준비(기록
    자리)가 서로 다른 카드에 있었다.

    그리고 하나는 아무 데도 없었다 - 언제 지은 판인가. Sprint201에서
    dist의 exe가 하루 지난 것이었고 Sprint192~200이 빠져 있었는데,
    그것을 알아챈 것은 사람이 날짜를 눈으로 본 덕이었다.

    app_info.build_date()는 이미 있다. 어느 화면도 쓰지 않았을 뿐이다.
    """

    def card(self):
        from app.services import beta_release_candidate

        return beta_release_candidate.build(self.store, None)

    def test_the_card_carries_a_start_check(self):
        self.assertIn("start_check", self.card())

    def test_it_says_whether_the_folder_is_whole(self):
        from app.services import beta_package_validation

        found = self.card()["start_check"]["package"]
        theirs = beta_package_validation.build()

        for key in ("passed", "failed", "unknown"):
            with self.subTest(key=key):
                self.assertEqual(found[key], theirs[key])

    def test_the_missing_rows_are_the_ones_that_failed(self):
        from app.services import beta_package_validation

        theirs = beta_package_validation.build()

        gone = [row["label"] for group in theirs["groups"]
                for row in group["checks"] if row["ok"] is False]

        self.assertEqual(self.card()["start_check"]["package"]["missing"],
                         gone)

    def test_it_says_when_this_build_was_made(self):
        from app import app_info

        found = self.card()["start_check"]["built_at"]

        self.assertEqual(found, app_info.build_date())

    def test_never_bundled_is_not_a_failure(self):
        """
        개발 중에는 묶은 적이 없다. X로 찍으면 고장 난 것으로 읽힌다.
        """

        said = self.card()["start_check"]["built_detail"]

        self.assertIn("묶은 적이 없습니다", said)

    def test_it_says_where_received_records_go(self):
        from app.services import beta_dashboard

        self.some()

        found = self.card()["start_check"]["collecting"]

        self.assertEqual(found["dirname"],
                         beta_dashboard.build()["collected_dirname"])

    def test_it_says_how_many_have_come_so_far(self):
        from app.services import beta_summary

        self.some()

        self.assertEqual(self.card()["start_check"]["collecting"]["so_far"],
                         beta_summary.build()["installations"])


class TheDateIsNotAVerdictTest(Base):
    """
    Sprint208 - 날짜는 적을 뿐 판정하지 않는다.

    며칠이면 오래된 것인지 우리가 정할 일이 아니다. 정하는 순간 새
    기준이 생긴다.
    """

    def test_it_never_calls_the_build_old(self):
        from app.services import beta_release_candidate

        body = json.dumps(beta_release_candidate.build(self.store, None),
                          ensure_ascii=False)

        for said in ("오래", "낡", "최신이 아닙니다", "다시 묶"):
            with self.subTest(said=said):
                self.assertNotIn(said, body)

    def test_it_never_says_it_is_fine(self):
        from app.services import beta_release_candidate

        body = json.dumps(beta_release_candidate.build(self.store, None),
                          ensure_ascii=False)

        for said in ("통과", "배포 가능", "문제 없음", "안전함"):
            with self.subTest(said=said):
                self.assertNotIn(said, body)


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
