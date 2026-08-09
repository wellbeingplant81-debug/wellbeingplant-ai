"""
Sprint191 - 지금 내보낼 수 있는 상태인가 (Epic 59, Phase 14).

체크마크는 지어내면 안 된다
---------------------------
"O 무료 제작 흐름"이라고 찍어 놓고 그 근거가 없으면, 그 화면은
사람을 안심시키는 그림일 뿐이다. 그래서 여기 있는 줄은 전부 지금
이 자리에서 실제로 확인할 수 있는 사실이다.

    실행파일        묶인 프로그램으로 돌고 있는가        runtime_paths
    데이터 분리     내 것이 프로그램 폴더 밖에 있는가    runtime_paths
    무료 제작 흐름  대본까지 간 기록이 있는가            beta_summary
    렌더 완료       끝까지 간 기록이 있는가              beta_summary
    진단 정보       판번호를 담아 답하는가               diagnostic_report
    피드백 자리     그 폴더가 있는가                     runtime_paths

셋째와 넷째가 중요하다. "기능이 있다"가 아니라 "실제로 그렇게 된
기록이 있다"이다 - 있다고 말할 수 있는 것은 그것뿐이다.

모르는 것은 모른다고 한다
-------------------------
테스트 결과 파일은 이 저장소에 없다. 그것을 X로 찍으면 "실패했다"로
읽히고, O로 찍으면 거짓이다. 그래서 셋째 값(None)을 쓴다.

다 통과해도 "준비 완료"라고 하지 않는다
---------------------------------------
여기 있는 여섯 줄이 전부 O여도, 그것은 이 여섯 가지가 확인됐다는
뜻이지 내보내도 된다는 뜻이 아니다. 그 말을 payload가 직접 한다.
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
from app.services import beta_dashboard, beta_readiness, beta_telemetry

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

    def rows(self, found=None):
        found = found or beta_readiness.build()

        return {row["key"]: row for row in found["checks"]}

    def now(self):
        return beta_readiness.build()


class ShapeTest(Base):
    """1. 여섯 줄과 세 묶음."""

    def test_the_groups_are_the_declared_ones(self):
        found = self.now()

        self.assertEqual(
            sorted({row["group"] for row in found["checks"]}),
            sorted(["배포", "제작", "운영"]))

    def test_every_row_carries_what_the_screen_draws(self):
        for row in self.now()["checks"]:
            with self.subTest(row=row["key"]):
                self.assertEqual(sorted(row),
                                 ["detail", "group", "key", "label", "ok"])
                self.assertTrue(row["label"])
                self.assertTrue(row["detail"])

    def test_the_version_is_the_one_everybody_says(self):
        self.assertEqual(self.now()["version"], app_info.VERSION)


class EvidenceTest(Base):
    """2. 근거가 있는 것만 O."""

    def test_running_from_source_is_not_a_packaged_program(self):
        """
        개발 중에는 '실행파일'이 O가 아니다.

        여기서 O를 찍으면 그 화면은 묶어 보지도 않고 "됐다"고 말한다.
        """

        with patch.object(runtime_paths, "is_frozen", return_value=False):
            self.assertFalse(self.rows()["executable"]["ok"])

        with patch.object(runtime_paths, "is_frozen", return_value=True):
            self.assertTrue(self.rows()["executable"]["ok"])

    def test_the_free_flow_needs_a_record_not_a_feature(self):
        """
        "기능이 있다"가 아니라 "그렇게 된 기록이 있다"이다.
        """

        self.assertFalse(self.rows()["free_flow"]["ok"])

        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)

        self.assertTrue(self.rows()["free_flow"]["ok"])

    def test_the_render_row_needs_a_finished_one(self):
        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_STARTED)

        self.assertFalse(self.rows()["render_done"]["ok"])

        self.sent("을.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_COMPLETED)

        self.assertTrue(self.rows()["render_done"]["ok"])

    def test_the_feedback_place_is_looked_at_not_assumed(self):
        self.assertFalse(self.rows()["feedback_place"]["ok"])

        runtime_paths.ensure(runtime_paths.feedback_root())

        self.assertTrue(self.rows()["feedback_place"]["ok"])

    def test_the_data_is_separated_when_home_is_outside_the_program(self):
        rows = self.rows()

        self.assertTrue(rows["data_separated"]["ok"])

        with patch.object(runtime_paths, "program_dir",
                          return_value=self.home):
            self.assertFalse(self.rows()["data_separated"]["ok"])

    def test_the_diagnostic_row_says_what_it_actually_checked(self):
        """
        이 줄은 "판번호를 담아 답하는가"뿐이다.

        그 이상을 확인하지 않았으므로 그 이상을 적지 않는다.
        """

        row = self.rows()["diagnostic"]

        self.assertTrue(row["ok"])
        self.assertIn("판번호", row["detail"])


class UnknownTest(Base):
    """3. 모르는 것은 모른다고 한다."""

    def test_a_missing_test_report_is_unknown_not_failed(self):
        """
        X로 찍으면 "실패했다"로 읽히고, O로 찍으면 거짓이다.
        """

        row = self.rows()["test_report"]

        self.assertIsNone(row["ok"])
        self.assertIn("없", row["detail"])

    def test_a_report_that_exists_is_read_not_judged(self):
        path = os.path.join(self.home, "테스트결과.txt")

        with open(path, "w", encoding="utf-8") as f:
            f.write("OK - ran=4031 failures=0 errors=0")

        with patch.object(beta_readiness, "test_report_path",
                          return_value=path):
            row = self.rows()["test_report"]

        self.assertTrue(row["ok"])
        self.assertIn("4031", row["detail"])

    def test_a_failing_report_is_not_dressed_up(self):
        path = os.path.join(self.home, "테스트결과.txt")

        with open(path, "w", encoding="utf-8") as f:
            f.write("FAILED - ran=4031 failures=2 errors=0")

        with patch.object(beta_readiness, "test_report_path",
                          return_value=path):
            row = self.rows()["test_report"]

        self.assertFalse(row["ok"])


class NoOverclaimTest(Base):
    """4. 다 통과해도 '준비 완료'라고 하지 않는다."""

    def test_it_never_says_ready_to_ship(self):
        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_COMPLETED)
        runtime_paths.ensure(runtime_paths.feedback_root())

        with patch.object(runtime_paths, "is_frozen", return_value=True):
            found = self.now()

        body = json.dumps(found, ensure_ascii=False)

        for claim in ("배포해도 됩니다", "준비 완료", "이상 없음"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, body)

        self.assertTrue(found["caution"])
        self.assertIn("확인된", found["caution"])

    def test_it_counts_what_passed_without_calling_it_a_verdict(self):
        found = self.now()

        self.assertEqual(found["passed"] + found["failed"]
                         + found["unknown"], len(found["checks"]))


class WarningTest(Base):
    """5. 주의사항은 이미 나온 것만."""

    def test_the_notes_come_from_the_summary(self):
        from app.services import beta_summary

        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED)

        found = self.now()

        for note in beta_summary.build()["notes"]:
            with self.subTest(note=note):
                self.assertIn(note, found["warnings"])

    def test_a_missing_tool_is_a_warning(self):
        from app.services import media_tools

        with patch.object(media_tools, "missing",
                          return_value=["ffprobe"]):
            found = self.now()

        self.assertTrue(any("ffprobe" in line
                            for line in found["warnings"]))


class QuietTest(Base):
    """6. 읽기만 한다."""

    def test_nothing_is_written(self):
        beta_telemetry.launched()

        before = sorted(os.listdir(self.home))

        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_new_event(self):
        beta_telemetry.launched()

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

    def test_nothing_personal(self):
        beta_telemetry.launched()
        runtime_paths.ensure(runtime_paths.feedback_root())

        body = json.dumps(self.now(), ensure_ascii=False)

        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))


class ApiTest(Base):
    """7. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/beta-readiness")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("version", "checks", "warnings", "caution",
                    "passed", "failed", "unknown"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        found = self.client.get("/studio/api/beta-readiness").json()

        self.assertEqual([row["key"] for row in found["checks"]],
                         [row["key"] for row in
                          beta_readiness.build()["checks"]])

    def test_the_screen_has_the_card(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-readiness", page)
        self.assertIn("Beta Readiness", page)
        self.assertIn("row.ok", page)


if __name__ == "__main__":
    unittest.main()
