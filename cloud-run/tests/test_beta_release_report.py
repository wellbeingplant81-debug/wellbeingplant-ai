"""
Sprint193 - 밖으로 내보낼 한 장 (Epic 59, Phase 16).

Beta Snapshot은 우리가 보는 화면이다. 그것을 남에게 보내려면 붙여넣을
수 있는 글이어야 하고, 밖으로 나가도 되는 것만 들어 있어야 한다.

스냅샷이 낸 것만 쓴다
---------------------
여기서 세지도 고르지도 않는다. 숫자 하나를 더하는 순간, 이 글과 그
화면이 다른 말을 하게 된다 - 그리고 받아 본 사람은 어느 쪽이 맞는지
알 수 없다.

그 사실을 테스트가 두 가지로 지킨다.

    1. 스냅샷을 통째로 넣어 주면 그 값이 그대로 나온다
    2. 소스에 다른 서비스 이름이 없다

밖으로 나가는 글이다
--------------------
경로도 파일명도 프로젝트명도 피드백 내용도 들어가지 않는다. 스냅샷이
애초에 담지 않지만, 여기서도 확인한다 - 이 글은 우리 손을 떠난다.
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
    beta_dashboard, beta_release_report, beta_snapshot, beta_telemetry,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _snapshot(**changed):
    """beta_snapshot이 내는 모양 그대로."""

    found = {
        "taken_at": "2026-08-09T21:00:00",
        "version": app_info.VERSION,
        "installations": 5,
        "flow": [
            {"key": "start", "label": "시작", "count": 5},
            {"key": "workspace_selected", "label": "자료 연결", "count": 4},
            {"key": "script_ready", "label": "대본 준비", "count": 2},
            {"key": "render_started", "label": "제작 시작", "count": 1},
            {"key": "render_completed", "label": "렌더 완료", "count": 1},
        ],
        "readiness": {
            "checks": [
                {"group": "배포", "key": "executable", "label": "실행파일",
                 "ok": True, "detail": "묶인 프로그램으로 돌고 있는지 봅니다."},
                {"group": "제작", "key": "free_flow",
                 "label": "무료 제작 흐름", "ok": False,
                 "detail": "대본까지 간 기록 0벌."},
                {"group": "운영", "key": "test_report",
                 "label": "테스트 결과", "ok": None,
                 "detail": "적어 둔 테스트 결과가 없습니다."},
            ],
            "passed": 1, "failed": 1, "unknown": 1,
            "caution": "여기 있는 것은 지금 확인된 것뿐입니다.",
        },
        "warnings": ["배경 음악이 없어 영상을 만들 수 없습니다."],
        "note": "이 화면은 저장되지 않습니다.",
    }

    found.update(changed)

    return found


class ShapeTest(unittest.TestCase):
    """1. 무엇이 담기는가."""

    def test_it_carries_the_declared_fields(self):
        found = beta_release_report.build(_snapshot())

        for key in ("version", "checked_at", "readiness", "summary",
                    "funnel", "cautions", "report"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_readiness_counts_are_the_snapshot_counts(self):
        found = beta_release_report.build(_snapshot())

        self.assertEqual(found["readiness"]["passed"], 1)
        self.assertEqual(found["readiness"]["failed"], 1)
        self.assertEqual(found["readiness"]["unknown"], 1)

    def test_the_funnel_is_the_snapshot_flow(self):
        snapshot = _snapshot()

        found = beta_release_report.build(snapshot)

        self.assertEqual(found["funnel"],
                         [{"label": row["label"], "count": row["count"]}
                          for row in snapshot["flow"]])

    def test_the_cautions_carry_the_warnings_and_the_caution(self):
        snapshot = _snapshot()

        found = beta_release_report.build(snapshot)

        for line in snapshot["warnings"]:
            with self.subTest(line=line):
                self.assertIn(line, found["cautions"])

        self.assertIn(snapshot["readiness"]["caution"], found["cautions"])


class NoNewMathTest(unittest.TestCase):
    """2. 여기서 세지 않는다."""

    def test_the_numbers_are_whatever_the_snapshot_said(self):
        """
        스냅샷이 이상한 숫자를 줘도 그대로 낸다.

        여기서 고치면 이 글과 화면이 다른 말을 하게 되고, 받아 본
        사람은 어느 쪽이 맞는지 알 수 없다.
        """

        odd = _snapshot(installations=99)
        odd["readiness"]["passed"] = 7

        found = beta_release_report.build(odd)

        self.assertEqual(found["summary"]["installations"], 99)
        self.assertEqual(found["readiness"]["passed"], 7)
        self.assertIn("99", found["report"])

    def test_it_asks_nobody_else(self):
        import re

        source = os.path.join(REPO, "app", "services",
                              "beta_release_report.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        self.assertIn("beta_snapshot", code)

        # 스냅샷 말고 다른 자리에 물어보지 않는다.
        for forbidden in ("beta_dashboard", "beta_summary", "beta_funnel",
                          "beta_insights", "beta_telemetry",
                          "output_check", "final_check",
                          "open(", "listdir", "makedirs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class TextTest(unittest.TestCase):
    """3. 붙여 넣을 글."""

    def test_it_reads_like_a_report(self):
        found = beta_release_report.build(_snapshot())
        text = found["report"]

        self.assertTrue(text.startswith(f"{app_info.NAME} Beta Release "
                                        "Report"))

        for mark in (app_info.VERSION, "2026-08-09T21:00:00",
                     "실행파일", "무료 제작 흐름", "테스트 결과",
                     "자료 연결", "렌더 완료", "배경 음악"):
            with self.subTest(mark=mark):
                self.assertIn(mark, text)

    def test_the_three_marks_are_used(self):
        text = beta_release_report.build(_snapshot())["report"]

        for mark in ("O ", "X ", "? "):
            with self.subTest(mark=mark):
                self.assertIn(mark, text)

    def test_nothing_to_warn_about_says_so(self):
        found = beta_release_report.build(
            _snapshot(warnings=[]))

        self.assertIn(_snapshot()["readiness"]["caution"],
                      found["cautions"])


class PrivacyTest(unittest.TestCase):
    """4. 밖으로 나가는 글이다."""

    def test_nothing_personal_even_if_the_snapshot_slipped(self):
        """
        스냅샷이 애초에 담지 않지만 여기서도 확인한다.

        이 글은 우리 손을 떠난다.
        """

        found = beta_release_report.build(_snapshot())
        body = json.dumps(found, ensure_ascii=False)

        for leak in (os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", found["report"]))


class LiveTest(unittest.TestCase):
    """5. 실제 스냅샷에서."""

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_it_matches_the_snapshot(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        snapshot = beta_snapshot.build()
        found = beta_release_report.build(snapshot)

        self.assertEqual(found["version"], snapshot["version"])
        self.assertEqual(found["checked_at"], snapshot["taken_at"])
        self.assertEqual([row["count"] for row in found["funnel"]],
                         [row["count"] for row in snapshot["flow"]])

    def test_it_takes_its_own_snapshot_when_not_given_one(self):
        beta_telemetry.launched()

        found = beta_release_report.build()

        self.assertTrue(found["checked_at"])
        self.assertEqual(found["version"], app_info.VERSION)

    def test_nothing_is_written(self):
        beta_telemetry.launched()

        before = sorted(os.listdir(self.home))

        beta_release_report.build()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_new_event(self):
        beta_telemetry.launched()

        before = json.dumps(beta_telemetry.events(), ensure_ascii=False)

        beta_release_report.build()

        self.assertEqual(
            json.dumps(beta_telemetry.events(), ensure_ascii=False), before)

    def test_no_maker_is_called(self):
        from app.services import studio_jobs, studio_review

        with patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            beta_release_report.build()

            render.assert_not_called()
            start.assert_not_called()

    def test_no_personal_data_from_a_real_run(self):
        beta_telemetry.launched()

        folder = runtime_paths.ensure(runtime_paths.feedback_root())

        with open(os.path.join(folder, "무릎 안 됨.txt"), "w",
                  encoding="utf-8") as f:
            f.write(r"C:\Users\사람\내자료")

        text = beta_release_report.build()["report"]

        for leak in (self.home, "무릎", "내자료", "사람"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, text)


class ApiTest(unittest.TestCase):
    """6. 서버와 화면."""

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
        answer = self.client.get("/studio/api/beta-release-report")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("version", "checked_at", "readiness", "summary",
                    "funnel", "cautions", "report"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        beta_telemetry.launched()

        found = self.client.get("/studio/api/beta-release-report").json()

        self.assertEqual([row["count"] for row in found["funnel"]],
                         [row["count"] for row in
                          beta_release_report.build()["funnel"]])

    def test_the_screen_has_the_button(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-release-report", page)
        self.assertIn("Release Report 복사", page)


if __name__ == "__main__":
    unittest.main()
