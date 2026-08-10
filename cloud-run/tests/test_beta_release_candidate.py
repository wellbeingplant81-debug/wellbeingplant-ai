"""
Sprint200 - 처음 받아서 켠 사람이 끝까지 갈 수 있는가 (Epic 59, Phase 18).

Sprint191~199가 만든 것은 운영자가 보는 층이었다. 이번은 방향이 다르다.

가 봤다고 말하지 않는다
-----------------------
우리가 할 수 있는 것은 여덟 걸음 각각에 "지금 확인되는 것", "아직 세는
자리가 없는 것", "다음에 할 일"을 늘어놓는 것뿐이다. 그래서 이 표는
"통과"라고 말하지 않는다.

없는 이름을 쓰지 않는다
-----------------------
자료가 갖춰졌다는 사건의 이름은 preparation_ready 다. asset_ready 가
아니다. 그리고 beta_dashboard는 그것을 모아 세지 않는다 - 다섯만
센다. 그래서 다섯째 걸음에는 댈 숫자가 없고, 그 자리는 ? 로 둔다.

X로 찍으면 "실패했다"로 읽히고 O로 찍으면 거짓이다.

여기서 > 0 을 만들지 않는다
---------------------------
그 비교 자체가 새 기준이다. beta_readiness가 이미 script_ready > 0을
판정해 free_flow 줄에 담아 두었다. 그 답을 옮기는 것과 여기서 다시
재는 것은 다르다.
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

from app import runtime_paths
from app.routers import studio as studio_router
from app.services import (
    beta_dashboard, beta_release_candidate, beta_release_gate, beta_telemetry,
    onboarding_state,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 최종 판단을 뜻하는 말. 전부 긍정형이다 - caution의 부정문에 걸리지
# 않게 하려는 것이다(Sprint199에서 겪음).
NEVER_SAID = ("통과", "배포 가능", "문제 없음", "안전함", "출시 준비 완료")

# 다섯째 걸음. 모아 세는 자리가 없다.
ASSETS = "assets"


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        self.store = runtime_paths.ensure(
            os.path.join(self.home, "store"))

    def sent(self, name, *events, error=None):
        folder = runtime_paths.ensure(beta_dashboard.collected_root())

        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "launch_count": 1,
                       "first_launch_at": None, "last_launch_at": None,
                       "events": [{"event": e,
                                   "timestamp": "2026-08-10T10:00:00",
                                   "version": "0.1.0"} for e in events],
                       "seen": [], "last_error_kind": error,
                       "last_error_time": None}, f, ensure_ascii=False)

    def walked(self):
        """정상 흐름 - 자료 갖춤까지 지나서 끝까지 간 사람."""

        beta_telemetry.launched()

        self.sent("갑.json",
                  beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.PREPARATION_READY)
        self.sent("을.json",
                  beta_telemetry.WORKSPACE_SELECTED,
                  beta_telemetry.SCRIPT_READY,
                  beta_telemetry.PREPARATION_READY,
                  beta_telemetry.RENDER_STARTED,
                  beta_telemetry.RENDER_COMPLETED)

    def now(self, project_path=None):
        return beta_release_candidate.build(self.store, project_path)

    def step(self, found, key):
        for row in found["journey"]:
            if row["key"] == key:
                return row

        raise AssertionError(f"걸음이 없습니다: {key}")


class FirstRunTest(Base):
    """A. 아무것도 없는 사람."""

    def test_it_says_first_run(self):
        found = self.now()

        self.assertEqual(found["now"]["state"], onboarding_state.FIRST_RUN)

    def test_it_says_what_to_do_next(self):
        found = self.now()

        self.assertTrue((found["now"]["next_action"] or "").strip())

    def test_nothing_personal(self):
        beta_telemetry.launched()

        folder = runtime_paths.ensure(runtime_paths.feedback_root())

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


class TheWalkTest(Base):
    """B. 여덟 걸음."""

    def test_it_has_eight_steps(self):
        found = self.now()

        self.assertEqual(len(found["journey"]), 8)

    def test_the_counts_are_the_gate_counts(self):
        self.walked()

        found = self.now()
        gate = beta_release_gate.build()

        theirs = {row["label"]: row["count"]
                  for row in gate["release"]["funnel"]}

        for key, label in (("first_run", "시작"),
                           ("workspace", "자료 연결"),
                           ("script", "대본 준비"),
                           ("render_started", "제작 시작"),
                           ("render_completed", "렌더 완료")):
            with self.subTest(key=key):
                self.assertEqual(self.step(found, key)["count"], theirs[label])

    def test_the_readiness_marks_are_the_gate_marks(self):
        self.walked()

        found = self.now()
        gate = beta_release_gate.build()

        marks = {row["key"]: row["ok"] for row in gate["readiness"]["checks"]}

        self.assertEqual(self.step(found, "install")["ok"],
                         marks["executable"])
        self.assertEqual(self.step(found, "script")["ok"], marks["free_flow"])
        self.assertEqual(self.step(found, "render_completed")["ok"],
                         marks["render_done"])

    def test_the_assets_step_says_it_does_not_know(self):
        """
        preparation_ready는 기록에 남지만 모아 세는 자리가 없다.
        """

        self.walked()

        row = self.step(self.now(), ASSETS)

        self.assertIsNone(row["ok"])
        self.assertIsNone(row["count"])
        self.assertIn("세는", row["detail"])

    def test_the_state_is_the_onboarding_state(self):
        self.walked()

        found = self.now()
        theirs = onboarding_state.build(self.store, None)

        self.assertEqual(found["now"]["state"], theirs["state"])
        self.assertEqual(found["now"]["next_action"], theirs["next_action"])


class WhenItBreaksTest(Base):
    """C. 잘못된 자리, 깨진 기록, 실패한 렌더."""

    def test_a_broken_record_does_not_kill_it(self):
        folder = runtime_paths.ensure(beta_dashboard.collected_root())

        with open(os.path.join(folder, "깨짐.json"), "w",
                  encoding="utf-8") as f:
            f.write("{ 이건 json이 아니다")

        found = self.now()

        self.assertIn("journey", found)

    def test_a_missing_folder_does_not_kill_it(self):
        found = beta_release_candidate.build(
            os.path.join(self.home, "없는자리"), None)

        self.assertIn("journey", found)

    def test_the_error_kinds_are_the_gate_kinds(self):
        beta_telemetry.launched()
        self.sent("병.json", beta_telemetry.WORKSPACE_SELECTED,
                  error="ffmpeg_missing")

        found = self.now()
        gate = beta_release_gate.build()

        self.assertEqual(found["errors"], gate["summary"]["error_kinds"])

    def test_no_path_reaches_the_report(self):
        beta_telemetry.launched()
        self.sent("정.json", beta_telemetry.WORKSPACE_SELECTED,
                  error="ffmpeg_missing")

        body = json.dumps(self.now(), ensure_ascii=False)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))
        self.assertNotIn("Traceback", body)


class RunAgainTest(Base):
    """D. 두 번째 실행."""

    def test_nothing_is_written(self):
        self.walked()

        before = sorted(os.listdir(self.home))

        self.now()
        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_new_event(self):
        self.walked()

        before = json.dumps(beta_telemetry.events(), ensure_ascii=False)

        self.now()

        self.assertEqual(
            json.dumps(beta_telemetry.events(), ensure_ascii=False), before)

    def test_the_record_is_read_once(self):
        self.walked()

        with patch.object(beta_dashboard, "build",
                          wraps=beta_dashboard.build) as counted:
            self.now()

            self.assertEqual(counted.call_count, 1)


class NoNewJudgementTest(Base):
    """E. 판정하지 않는다."""

    def test_it_never_says_it_passed(self):
        self.walked()

        body = json.dumps(self.now(), ensure_ascii=False)

        for said in NEVER_SAID:
            with self.subTest(said=said):
                self.assertNotIn(said, body)

    def test_the_caution_is_carried(self):
        from app.services import beta_readiness

        self.assertIn(beta_readiness.CAUTION, self.now()["cautions"])

    def test_it_does_not_count_anything(self):
        source = os.path.join(REPO, "app", "services",
                              "beta_release_candidate.py")

        with open(source, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        counted = [node.func.id for node in ast.walk(tree)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id in ("sum", "len", "max", "min", "sorted")]

        self.assertEqual(counted, [])

    def test_it_asks_only_the_places_it_should(self):
        import re

        source = os.path.join(REPO, "app", "services",
                              "beta_release_candidate.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for wanted in ("beta_release_gate", "onboarding_state"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        # Gate가 이미 기록을 한 번만 읽고 그 결과를 들고 있다. 다시
        # 부르면 그것이 두 번째 읽기가 된다.
        for forbidden in ("beta_summary", "beta_readiness", "beta_dashboard",
                          "beta_funnel", "open(", "listdir", "makedirs",
                          "record("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class EveryStateSaysWhatToDoTest(unittest.TestCase):
    """F. 어디에서 막혀도 다음 행동이 있다."""

    def test_every_state_has_a_next_action(self):
        """
        막힌 자리에서 할 말이 없으면 사람은 창을 닫는다.
        """

        for state, (title, message, action, _) in \
                onboarding_state.SAYS.items():
            with self.subTest(state=state):
                self.assertTrue(title.strip())
                self.assertTrue(message.strip())
                self.assertTrue(action.strip())


class ApiTest(Base):
    """G. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/beta-release-candidate")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("taken_at", "now", "journey", "errors", "cautions",
                    "note"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_screen_has_the_button(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-release-candidate", page)
        self.assertIn("처음 사용자 테스트", page)


if __name__ == "__main__":
    unittest.main()
