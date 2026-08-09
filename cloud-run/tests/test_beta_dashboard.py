"""
Sprint184 - 베타가 어디에서 멈추는지 한눈에 (Epic 59, Phase 7).

기록은 설치본마다 하나다
------------------------
beta_usage.json은 그 사람의 PC에만 있다. 그래서 이 화면을 그냥 만들면
"사용자 1명"이라고만 나온다 - 우리 것 하나뿐이기 때문이다.

그것을 "사용자 수"라고 부르면 거짓이 된다. 그래서 두 가지를 한다.

    1. 받은 기록을 모아 둘 자리를 만든다  <관측 기록>/collected/
    2. 몇 벌을 보고 세었는지 함께 말한다  installations

보내온 파일을 그 폴더에 넣으면 그때부터 세어진다. 아무것도 안 넣으면
내 것 하나를 센 것이고, 화면이 그렇게 말한다.

세기만 한다
-----------
판정하지 않는다. 어느 단계까지 갔는지는 beta_telemetry가 적어 둔
사건 이름의 차례로만 정한다.
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
from app.services import beta_dashboard, beta_telemetry

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def mine(self, *events, launches=1):
        """내 기록. beta_telemetry가 적는 그 자리다."""

        for _ in range(launches):
            beta_telemetry.launched()

        for name in events:
            beta_telemetry.record(name)

    def sent(self, name, *events, launches=1):
        """다른 사람이 보내온 기록을 모아 둔 자리에 넣는다."""

        folder = runtime_paths.ensure(beta_dashboard.collected_root())

        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            json.dump({
                "version": 1,
                "launch_count": launches,
                "first_launch_at": "2026-08-09T10:00:00",
                "last_launch_at": "2026-08-09T11:00:00",
                "events": [{"event": e, "timestamp": "2026-08-09T10:30:00",
                            "version": "0.1.0"} for e in events],
                "seen": [],
                "last_error_kind": None,
                "last_error_time": None,
            }, f, ensure_ascii=False)

    def now(self):
        return beta_dashboard.build()


class CountTest(Base):
    """1. 세는 것."""

    def test_an_empty_install_says_nothing_happened(self):
        found = self.now()

        self.assertEqual(found["installations"], 0)
        self.assertEqual(found["users_started"], 0)
        self.assertEqual(found["render_completed"], 0)

    def test_it_counts_my_own_record(self):
        self.mine(beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)

        found = self.now()

        self.assertEqual(found["installations"], 1)
        self.assertEqual(found["users_started"], 1)
        self.assertEqual(found["workspace_selected"], 1)
        self.assertEqual(found["script_ready"], 1)
        self.assertEqual(found["render_completed"], 0)

    def test_it_counts_the_records_people_sent(self):
        """
        받은 기록을 모아 둔 자리에 넣으면 그때부터 세어진다.

        그 전까지는 내 것 하나뿐이고, 화면이 그렇게 말한다.
        """

        self.mine(beta_telemetry.WORKSPACE_SELECTED)
        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_COMPLETED)
        self.sent("을.json", beta_telemetry.WORKSPACE_SELECTED)

        found = self.now()

        self.assertEqual(found["installations"], 3)
        self.assertEqual(found["users_started"], 3)
        self.assertEqual(found["workspace_selected"], 3)
        self.assertEqual(found["script_ready"], 1)
        self.assertEqual(found["render_completed"], 1)

    def test_the_total_runs_are_added_up(self):
        self.mine(launches=3)
        self.sent("갑.json", launches=5)

        self.assertEqual(self.now()["launch_count"], 8)

    def test_a_broken_file_is_skipped_not_fatal(self):
        """
        보내온 파일 하나가 깨져 있어도 나머지는 세어진다.

        여기서 죽으면 화면 전체가 안 뜬다.
        """

        self.mine(beta_telemetry.WORKSPACE_SELECTED)

        folder = runtime_paths.ensure(beta_dashboard.collected_root())

        with open(os.path.join(folder, "깨진것.json"), "w",
                  encoding="utf-8") as f:
            f.write("{ 이건 기록이 아니다")

        found = self.now()

        self.assertEqual(found["installations"], 1)
        self.assertEqual(found["unreadable"], 1)


class BlockedTest(Base):
    """2. 어디에서 멈췄는가."""

    def test_each_record_is_counted_where_it_stopped(self):
        self.mine()                                     # 아무것도 안 함
        self.sent("갑.json", beta_telemetry.WORKSPACE_SELECTED)
        self.sent("을.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)
        self.sent("병.json", beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_COMPLETED)

        found = self.now()["blocked_stage"]

        # 켜기만 한 것(내 것) · 폴더까지(갑) · 대본까지(을) ·
        # 끝까지(병).
        self.assertEqual(found["start"], 1)
        self.assertEqual(found[beta_dashboard.WORKSPACE_SELECTED], 1)
        self.assertEqual(found[beta_dashboard.SCRIPT_READY], 1)
        self.assertEqual(found[beta_dashboard.DONE], 1)

        # 병은 render_started 없이 완료됐다. 끝까지 간 것은 막힌 것이
        # 아니므로 여기서 세지 않는다.
        self.assertEqual(found[beta_dashboard.RENDER_STARTED], 0)

    def test_a_finished_one_is_not_blocked(self):
        self.mine(beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_COMPLETED)

        found = self.now()

        self.assertEqual(found["blocked_stage"][beta_dashboard.DONE], 1)
        self.assertEqual(found["render_completed"], 1)

    def test_every_stage_has_a_slot(self):
        """
        아무도 없는 단계도 0으로 적는다.

        없는 줄이 사라지면 "그 단계가 없다"로 읽힌다.
        """

        found = self.now()["blocked_stage"]

        for stage in beta_dashboard.STAGES:
            with self.subTest(stage=stage):
                self.assertIn(stage, found)

    def test_a_failed_render_is_counted(self):
        self.mine(beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_FAILED)

        found = self.now()

        self.assertEqual(found["render_failed"], 1)
        self.assertEqual(found["blocked_stage"][beta_dashboard.DONE], 0)


class PrivacyTest(Base):
    """3. 남의 것이 들어가지 않는다."""

    def test_nothing_personal_in_the_numbers(self):
        self.mine(beta_telemetry.WORKSPACE_SELECTED)
        self.sent("사람이름.json", beta_telemetry.SCRIPT_READY)

        body = json.dumps(self.now(), ensure_ascii=False)

        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME",
                     "사람이름"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))

    def test_it_writes_nothing(self):
        self.mine(beta_telemetry.WORKSPACE_SELECTED)

        before = sorted(os.listdir(self.home))

        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_it_judges_nothing_by_itself(self):
        import re

        source = os.path.join(REPO, "app", "services", "beta_dashboard.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        self.assertIn("beta_telemetry", code)

        for forbidden in ("generate_", "atomic_write", "makedirs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)

    def test_it_never_touches_the_makers(self):
        from app.services import studio_jobs, studio_review

        self.mine(beta_telemetry.WORKSPACE_SELECTED)

        with patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            self.now()

            render.assert_not_called()
            start.assert_not_called()


class ApiTest(Base):
    """4. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_the_api_answers(self):
        self.mine(beta_telemetry.WORKSPACE_SELECTED)

        answer = self.client.get("/studio/api/beta-dashboard")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("users_started", "workspace_selected", "script_ready",
                    "render_started", "render_completed", "blocked_stage",
                    "installations"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        self.mine(beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY)

        self.assertEqual(
            self.client.get("/studio/api/beta-dashboard").json()["script_ready"],
            beta_dashboard.build()["script_ready"])

    def test_the_screen_has_the_panel(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-dashboard", page)
        self.assertIn("베타 현황", page)

    def test_the_screen_says_how_many_records_it_counted(self):
        """
        몇 벌을 보고 센 것인지 화면이 말한다.

        내 것 하나만 보고 "사용자 1명"이라고 하면, 읽는 사람은 베타
        참가자가 한 명뿐이라고 오해한다.
        """

        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("installations", page)


if __name__ == "__main__":
    unittest.main()
