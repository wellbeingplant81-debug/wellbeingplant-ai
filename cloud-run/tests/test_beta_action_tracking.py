"""
Sprint187 - 도움말이 가리킨 걸음에 닿았는가 (Epic 59, Phase 10).

Sprint186이 "어느 안내를 열면 되는가"를 가리켜 줬다. 그 다음 물음은
"그래서 넘어갔는가"다.

말할 수 없는 것을 말하지 않는다
-------------------------------
도움말을 언제 열었는지는 적지 않기로 했다(새 기록 금지). 그러면
"도움말을 보고 넘어갔다"는 말은 할 수 없다 - 그 사이에 무슨 일이
있었는지 우리가 모르기 때문이다.

그래서 이 자리가 말하는 것은 하나뿐이다.

    도움말이 가리킨 그 걸음에 닿은 적이 있는가

닿았다는 것과 도움말 덕분이라는 것은 다르다. 그 차이를 payload가
직접 말한다 - 화면이 "도움말 효과"로 읽지 않게.

새로 판정하지 않는다
--------------------
    beta_actions       무엇을 가리켰는가
    beta_telemetry     그 걸음에 닿은 적이 있는가
    onboarding_state   지금 어디에 있는가
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
from app.services import (
    beta_action_tracking, beta_actions, beta_dashboard, beta_telemetry,
    first_run_guide,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def walked(self, *events):
        beta_telemetry.launched()

        for name in events:
            beta_telemetry.record(name)

    def now(self):
        return beta_action_tracking.build()


class MappingTest(unittest.TestCase):
    """1. 어느 걸음을 보아야 하는가."""

    def test_every_guide_step_we_point_at_has_an_event(self):
        """
        가리킬 수 있는 걸음마다 "닿았다"를 잴 사건이 있어야 한다.

        없으면 화면이 영영 "아직"이라고만 말한다.
        """

        for stage, (target, step) in beta_actions.WHERE.items():
            if target != beta_actions.GUIDE:
                continue

            with self.subTest(stage=stage):
                self.assertIn(step, beta_action_tracking.REACHED_BY)

    def test_the_events_are_the_ones_telemetry_writes(self):
        for event in beta_action_tracking.REACHED_BY.values():
            with self.subTest(event=event):
                self.assertIn(event, beta_telemetry.EVENTS)


class ReachedTest(Base):
    """2. 닿았는가."""

    def test_not_yet_says_not_yet(self):
        self.walked(beta_telemetry.WORKSPACE_SELECTED)

        found = self.now()

        self.assertEqual(found["target_event"], beta_telemetry.SCRIPT_READY)
        self.assertFalse(found["reached"])
        self.assertIsNone(found["reached_at"])

    def test_reaching_it_is_seen(self):
        self.walked(beta_telemetry.WORKSPACE_SELECTED,
                    beta_telemetry.SCRIPT_READY)

        found = self.now()

        # 대본까지 갔으므로 이제 가리키는 것은 그 다음 걸음이다.
        self.assertEqual(found["help"]["stage"],
                         beta_dashboard.SCRIPT_READY)
        self.assertEqual(found["target_event"],
                         beta_telemetry.RENDER_STARTED)
        self.assertFalse(found["reached"])

    def test_a_past_step_is_remembered(self):
        """
        지나온 걸음은 닿은 적이 있는 것으로 남는다.

        기록에 적혀 있으므로 그것을 없다고 하지 않는다.
        """

        self.walked(beta_telemetry.WORKSPACE_SELECTED,
                    beta_telemetry.SCRIPT_READY)

        self.assertTrue(
            beta_action_tracking.reached(beta_telemetry.SCRIPT_READY)[0])

    def test_the_time_comes_from_the_record(self):
        self.walked(beta_telemetry.WORKSPACE_SELECTED)

        there, when = beta_action_tracking.reached(
            beta_telemetry.WORKSPACE_SELECTED)

        self.assertTrue(there)
        self.assertTrue(when)


class HonestyTest(Base):
    """3. 말할 수 없는 것을 말하지 않는다."""

    def test_it_never_claims_the_help_caused_it(self):
        """
        도움말을 언제 열었는지 적지 않으므로, 그 사이에 무슨 일이
        있었는지 우리는 모른다.

        payload가 그 사실을 직접 말한다 - 화면이 "도움말 효과"로
        읽지 않게.
        """

        self.walked(beta_telemetry.WORKSPACE_SELECTED,
                    beta_telemetry.SCRIPT_READY)

        found = self.now()

        self.assertTrue(found["caution"])
        self.assertIn("언제 열었는지", found["caution"])

        body = json.dumps(found, ensure_ascii=False)

        # 낱말을 맨 문자열로 찾지 않는다 - caution 자체가 "도움말
        # 때문에 넘어갔다는 뜻은 아닙니다"라고 적혀 있어서, 부정문이
        # 걸린다. 막으려는 것은 단정이므로 단정하는 모양으로 본다.
        for claim in ("도움말 덕분", "도움말 효과",
                      "때문에 넘어갔습니다", "때문에 이동"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, body)

        # 부정하는 말은 반드시 있어야 한다.
        self.assertIn("뜻은 아닙니다", found["caution"])

    def test_no_record_is_added(self):
        """
        보기만 한다. 물어봤다고 새 사건이 적히지 않는다.
        """

        self.walked(beta_telemetry.WORKSPACE_SELECTED)

        before = json.dumps(beta_telemetry.events(), ensure_ascii=False)

        self.now()

        self.assertEqual(
            json.dumps(beta_telemetry.events(), ensure_ascii=False), before)

    def test_nothing_is_written(self):
        self.walked(beta_telemetry.WORKSPACE_SELECTED)

        before = sorted(os.listdir(self.home))

        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_it_writes_nothing_and_judges_nothing(self):
        import re

        source = os.path.join(REPO, "app", "services",
                              "beta_action_tracking.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for wanted in ("beta_actions", "beta_telemetry"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        for forbidden in ("open(", "listdir", "json.load", "makedirs",
                          "record(", "launched(", "failed(", "generate_"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class NoHelpTest(Base):
    """4. 가리킬 것이 없을 때."""

    def test_nothing_to_point_at_means_nothing_to_measure(self):
        found = self.now()

        self.assertIsNone(found["target_event"])
        self.assertFalse(found["reached"])
        self.assertTrue(found["help"])

    def test_a_finished_one_has_nothing_to_measure(self):
        self.walked(beta_telemetry.WORKSPACE_SELECTED,
                    beta_telemetry.SCRIPT_READY,
                    beta_telemetry.RENDER_STARTED,
                    beta_telemetry.RENDER_COMPLETED)

        found = self.now()

        self.assertIsNone(found["target_event"])

    def test_the_trouble_target_is_measured_by_a_finished_render(self):
        self.walked(beta_telemetry.WORKSPACE_SELECTED,
                    beta_telemetry.SCRIPT_READY,
                    beta_telemetry.RENDER_STARTED)

        found = self.now()

        self.assertEqual(found["help"]["action"]["target"],
                         beta_actions.TROUBLE)
        self.assertEqual(found["target_event"],
                         beta_telemetry.RENDER_COMPLETED)


class PrivacyTest(Base):
    """5. 남의 것이 들어가지 않는다."""

    def test_nothing_personal(self):
        self.walked(beta_telemetry.WORKSPACE_SELECTED)

        body = json.dumps(self.now(), ensure_ascii=False)

        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))

    def test_no_maker_is_called(self):
        from app.services import studio_jobs, studio_review

        self.walked(beta_telemetry.WORKSPACE_SELECTED)

        with patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            self.now()

            render.assert_not_called()
            start.assert_not_called()


class ApiTest(Base):
    """6. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/beta-action-progress")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("help", "target_event", "reached", "reached_at",
                    "caution"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        self.walked(beta_telemetry.WORKSPACE_SELECTED)

        self.assertEqual(
            self.client.get("/studio/api/beta-action-progress").json()
            ["target_event"],
            beta_action_tracking.build()["target_event"])

    def test_the_screen_has_the_place(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-action-progress", page)
        self.assertIn("도움말 이후 진행", page)


if __name__ == "__main__":
    unittest.main()
