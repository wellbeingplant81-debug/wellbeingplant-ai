"""
Sprint186 - 그래서 어느 안내를 보면 되는가 (Epic 59, Phase 9).

Sprint185가 "가장 많이 막힌 단계"를 알려 줬다. 그런데 그 다음에
무엇을 열어야 하는지는 여전히 사람이 찾아야 했다.

해결 방법을 새로 만들지 않는다
------------------------------
이미 있는 안내가 어디 있는지를 가리키기만 한다.

    first_run_guide   여섯 걸음 중 몇 번째를 보면 되는가
    troubleshooting   무엇이 문제이고 어떻게 하는가

여기서 새 문장을 쓰면 같은 이야기가 두 벌이 되고, 어느 날 한쪽만
바뀐다.

'막힌 단계'가 무슨 뜻인지 조심한다
----------------------------------
beta_dashboard의 blocked_stage는 "그 사건까지 갔고 그 다음으로 못
갔다"는 뜻이다. workspace_selected로 세어진 사람은 폴더를 이미
골랐고, 막힌 곳은 그 다음 걸음이다.

Sprint185의 안내문은 그것을 거꾸로 읽어 이미 끝낸 걸음을 가리키고
있었다. 여기서 함께 바로잡는다.
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
    beta_actions, beta_dashboard, beta_insights, beta_telemetry,
    first_run_guide,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _insights(top, tied=None, installations=3):
    """beta_insights가 내는 모양 그대로."""

    return {
        "top_blocked_stage": top,
        "top_candidates": tied or ([top] if top else []),
        "tied": bool(tied and len(tied) > 1),
        "stage_counts": {stage: 0 for stage in beta_dashboard.STAGES},
        "common_failures": [],
        "recommendations": [],
        "installations": installations,
        "thin": False,
        "enough": beta_insights.ENOUGH,
    }


class MappingTest(unittest.TestCase):
    """1. 어느 안내로 보내는가."""

    def test_every_stage_has_a_place_to_go(self):
        for stage in beta_dashboard.STAGES:
            with self.subTest(stage=stage):
                self.assertIn(stage, beta_actions.WHERE)

    def test_it_points_at_the_step_after_the_one_they_reached(self):
        """
        폴더를 이미 고른 사람에게 폴더 안내를 열어 주지 않는다.

        blocked_stage는 "그 사건까지 갔고 그 다음으로 못 갔다"는
        뜻이다 - 막힌 곳은 그 다음 걸음이다.
        """

        found = beta_actions.build(
            _insights(beta_dashboard.WORKSPACE_SELECTED))

        self.assertEqual(found["action"]["target"], "first_run_guide")
        self.assertEqual(found["action"]["step"], first_run_guide.SCRIPT)

    def test_someone_who_only_opened_it_is_sent_to_the_folder_step(self):
        found = beta_actions.build(_insights("start"))

        self.assertEqual(found["action"]["step"], first_run_guide.WORKSPACE)

    def test_a_script_that_never_became_a_video_goes_to_assets(self):
        found = beta_actions.build(_insights(beta_dashboard.SCRIPT_READY))

        self.assertEqual(found["action"]["step"], first_run_guide.ASSETS)

    def test_a_render_that_never_finished_goes_to_troubleshooting(self):
        """
        만들기 시작하고 못 끝낸 것은 안내가 아니라 문제 해결 쪽이다.
        """

        found = beta_actions.build(_insights(beta_dashboard.RENDER_STARTED))

        self.assertEqual(found["action"]["target"], "troubleshooting")

    def test_the_labels_name_a_screen_we_have(self):
        for stage in beta_dashboard.STAGES:
            with self.subTest(stage=stage):
                found = beta_actions.build(_insights(stage))

                if found["action"]:
                    self.assertIn(found["action"]["target"],
                                  beta_actions.TARGETS)
                    self.assertTrue(found["action"]["label"])


class NoGuessTest(unittest.TestCase):
    """2. 없는 것을 지어내지 않는다."""

    def test_nothing_blocked_means_no_action(self):
        found = beta_actions.build(_insights(None))

        self.assertIsNone(found["stage"])
        self.assertIsNone(found["action"])
        self.assertTrue(found["title"])

    def test_everyone_finished_means_no_action(self):
        found = beta_actions.build(_insights(beta_dashboard.DONE))

        self.assertIsNone(found["action"])

    def test_a_tie_is_not_resolved_here_either(self):
        """
        겹친 것 중에 하나를 골라 안내를 열어 주지 않는다.

        고르면 그것은 자료가 아니라 우리 취향이다 - Sprint185에서
        정한 그 규칙을 여기서도 지킨다.
        """

        found = beta_actions.build(_insights(
            None, tied=[beta_dashboard.WORKSPACE_SELECTED,
                        beta_dashboard.SCRIPT_READY]))

        self.assertIsNone(found["action"])
        self.assertTrue(found["tied"])
        self.assertEqual(len(found["candidates"]), 2)

    def test_no_data_says_so(self):
        found = beta_actions.build(_insights(None, installations=0))

        self.assertIsNone(found["action"])
        self.assertTrue(any("기록" in line for line in found["reasons"]))


class ReuseTest(unittest.TestCase):
    """3. 문장을 새로 쓰지 않는다."""

    def test_the_titles_come_from_the_guide(self):
        """
        걸음의 이름은 first_run_guide가 정한 것을 그대로 쓴다.

        여기서 다시 지으면 같은 걸음이 화면마다 다른 이름으로 뜬다.
        """

        found = beta_actions.build(
            _insights(beta_dashboard.WORKSPACE_SELECTED))

        title = next(row[1] for row in first_run_guide.STEPS
                     if row[0] == first_run_guide.SCRIPT)

        self.assertIn(title, found["title"])

    def test_it_writes_no_new_advice(self):
        import re

        source = os.path.join(REPO, "app", "services", "beta_actions.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for wanted in ("first_run_guide", "beta_dashboard"):
            with self.subTest(wanted=wanted):
                self.assertIn(wanted, code)

        for forbidden in ("open(", "listdir", "generate_", "makedirs",
                          "json.load"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class Sprint185FixTest(unittest.TestCase):
    """4. Sprint185의 안내문을 바로잡았다."""

    def test_the_recommendation_points_at_the_next_step(self):
        """
        폴더를 이미 고른 사람에게 폴더 안내를 보라고 하지 않는다.

        blocked_stage를 거꾸로 읽은 문장이었다.
        """

        told = beta_insights.WHERE_TO_LOOK[
            beta_dashboard.WORKSPACE_SELECTED][0]

        self.assertIn("대본", told)

    def test_the_start_stage_still_points_at_the_folder(self):
        told = beta_insights.WHERE_TO_LOOK["start"][0]

        self.assertIn("폴더", told)


class LiveTest(unittest.TestCase):
    """5. 실제 기록에서."""

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_it_reads_the_real_insights(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        found = beta_actions.build()

        self.assertEqual(found["stage"],
                         beta_dashboard.WORKSPACE_SELECTED)
        self.assertEqual(found["action"]["step"], first_run_guide.SCRIPT)

    def test_nothing_personal(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.WORKSPACE_SELECTED)

        body = json.dumps(beta_actions.build(), ensure_ascii=False)

        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))

    def test_nothing_is_written(self):
        beta_telemetry.launched()

        before = sorted(os.listdir(self.home))

        beta_actions.build()

        self.assertEqual(sorted(os.listdir(self.home)), before)

    def test_no_maker_is_called(self):
        from app.services import studio_jobs, studio_review

        beta_telemetry.launched()

        with patch.object(studio_review, "render") as render, \
                patch.object(studio_jobs, "start") as start:

            beta_actions.build()

            render.assert_not_called()
            start.assert_not_called()


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
        answer = self.client.get("/studio/api/beta-actions")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("stage", "title", "action"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_api_agrees_with_the_service(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.SCRIPT_READY)

        self.assertEqual(
            self.client.get("/studio/api/beta-actions").json()["stage"],
            beta_actions.build()["stage"])

    def test_the_screen_has_the_button(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-actions", page)
        self.assertIn("도움말 보기", page)


if __name__ == "__main__":
    unittest.main()
