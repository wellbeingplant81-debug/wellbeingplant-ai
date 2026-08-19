"""
Sprint226 - 시작한 일은 끝나고 나간다 (Epic 67).

무엇이 있었나
-------------
회귀가 돌릴 때마다 다른 답을 냈다. 추적기로 잡은 자리는 이렇다.

    [LATE .dataset] ...  thread=Thread-546 (_run)
      studio_jobs.py:369  in _run   beta_render_events.crashed(exc)
      beta_render_events.py:107     beta_telemetry.note(RENDER_FAILED)
      beta_telemetry.py:161  _save  runtime_paths.ensure(dataset_root())

POST /api/jobs 가 띄운 작업 스레드가 그것을 시작한 시험보다 오래 살아
있다가, 실패를 적으면서 **그때의** 사용자 자리를 다시 구했다. 그 자리가
다음 시험의 임시 집이면 거기에 .dataset 이 생기고, "읽어 보는 것만으로
아무것도 생기면 안 된다"는 무관한 시험이 깨진다.

시험이 옳았다. 치우지 않은 것이 잘못이었다.

여기서 지키는 것 둘
-------------------
    1. 기다릴 수 있는 문이 실제로 기다린다   settle()
    2. 실제로 작업을 시작하는 시험은 그 문을 반드시 지난다  (전수)

둘째를 글자로 훑지 않는다
-------------------------
"settle"을 grep 하면 이 파일의 설명에도 걸린다. 이 저장소가 여러 번
겪은 모양이라(test_subprocess_encoding · test_render_log_output) 부름식을
AST 로 본다.
"""

import ast
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import runtime_paths
from app.services import studio_jobs

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# start*() 다섯. 전부 스레드를 띄운다.
STARTERS = ("start", "start_regeneration", "start_oauth",
            "start_social", "start_upload")


# ══ 1. 문이 실제로 기다린다 ═════════════════════════════════════════

class TheDoorReallyWaitsTest(unittest.TestCase):
    """
    실제로 스레드를 띄워 본다. 대역으로 흉내 내면 이 문이 진짜
    기다리는지는 영영 모른다.
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="sprint226_")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        # 이 시험이 띄우는 작업도 관측을 적는다(beta_render_events).
        # 제 집을 주지 않으면 그것이 저장소 안에 쌓인다.
        moved = patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home})
        moved.start()
        self.addCleanup(moved.stop)

        self.let_go = threading.Event()
        self.arrived = threading.Event()

        self.addCleanup(self._release)
        self.addCleanup(studio_jobs.reset)

    def _release(self):
        self.let_go.set()
        studio_jobs.settle(timeout=30.0)

    def _start_a_job_that_waits(self):
        def holds_still(**asked):
            self.arrived.set()
            self.let_go.wait(timeout=30.0)

            raise RuntimeError("여기서 끝낸다")

        patcher = patch("app.services.factory_service.generate_short_video",
                        holds_still)
        patcher.start()
        self.addCleanup(patcher.stop)

        job_id = studio_jobs.start("주제", "wellbeing")

        self.assertTrue(self.arrived.wait(timeout=30.0),
                        "작업이 시작되지 않았다")

        return job_id

    def test_it_knows_what_is_actually_running(self):
        job_id = self._start_a_job_that_waits()

        self.assertIn(job_id, studio_jobs.running())

    def test_it_says_what_it_could_not_wait_for(self):
        """
        못 기다렸으면 못 기다렸다고 말한다. 삼키면 부르는 쪽은 다 끝난
        줄 안다.

        내가 띄운 것에 대해서만 말한다 - 이 문은 저장소 전체에 하나뿐
        이라 다른 시험이 남긴 것도 함께 돌아올 수 있고, 그것은 저 아래
        NoTestLeavesAJobRunningTest 가 볼 일이다.
        """

        job_id = self._start_a_job_that_waits()

        self.assertIn(job_id, studio_jobs.settle(timeout=0.2))

    def test_it_waits_until_the_job_is_over(self):
        job_id = self._start_a_job_that_waits()

        self.let_go.set()

        self.assertNotIn(job_id, studio_jobs.settle(timeout=30.0))
        self.assertNotIn(job_id, studio_jobs.running())

    def test_a_stand_in_thread_is_not_remembered(self):
        """
        Thread 자체를 대역으로 바꿔 놓고 부르는 자리가 있다(작업 기록만
        보는 시험들). 그 대역의 is_alive()는 무엇을 물어도 참 같은 것을
        돌려준다 - 그것을 적어 두면 running()이 영원히 "아직 돈다"고
        말한다. 실제로 그렇게 걸렸다.
        """

        with patch("app.services.studio_jobs.threading.Thread"):
            job_id = studio_jobs.start("주제", "wellbeing")

        self.assertNotIn(job_id, studio_jobs.running())
        self.assertEqual(studio_jobs.settle(timeout=0.2), [])

    def test_forgetting_the_record_does_not_stop_the_thread(self):
        """
        기록을 지우는 것과 스레드가 끝나는 것은 다른 일이다. 그 둘을
        같은 것으로 보았기 때문에 이 결함이 생겼다.
        """

        job_id = self._start_a_job_that_waits()

        studio_jobs.reset()

        self.assertIn(job_id, studio_jobs.running())


# ══ 2. 시작하는 시험은 그 문을 지난다 (전수) ════════════════════════

def _calls(tree):
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _starts_a_job_for_real(tree) -> bool:
    """
    실제로 스레드를 띄우는가.

    studio_jobs.start*() 를 직접 부르거나, POST /api/jobs 로 라우터를
    거쳐 같은 곳에 닿거나.
    """

    for node in _calls(tree):
        found = node.func

        if not isinstance(found, ast.Attribute):
            continue

        if (found.attr in STARTERS
                and isinstance(found.value, ast.Name)
                and found.value.id == "studio_jobs"):
            return True

        if found.attr == "post":
            for given in node.args:
                if (isinstance(given, ast.Constant)
                        and isinstance(given.value, str)
                        and given.value.rstrip("/").endswith("/api/jobs")):
                    return True

    return False


def _replaces_the_starter(tree) -> bool:
    """
    시작하는 함수 자체를 대역으로 바꿨는가. 그러면 스레드가 없다.

        patch("app.services.studio_jobs.start")
        patch.object(studio_jobs, "start")
    """

    for node in _calls(tree):
        found = node.func

        name = (found.attr if isinstance(found, ast.Attribute)
                else getattr(found, "id", ""))

        if name not in ("patch", "object"):
            continue

        given = [a.value for a in node.args
                 if isinstance(a, ast.Constant) and isinstance(a.value, str)]

        for one in given:
            tail = one.rsplit(".", 1)[-1]

            if tail in STARTERS and (one == tail or "studio_jobs" in one):
                return True

    return False


def _names_the_door(tree) -> bool:
    """settle() 을 부르는가. 글자가 아니라 부름식으로 본다."""

    for node in _calls(tree):
        found = node.func

        if isinstance(found, ast.Attribute) and found.attr == "settle":
            return True

    return False


def _left_open() -> dict:
    """{파일: 왜} - 실제로 시작하는데 문을 안 지나는 것들."""

    found = {}

    for name in sorted(os.listdir(TESTS_DIR)):
        if not name.startswith("test_") or not name.endswith(".py"):
            continue

        with open(os.path.join(TESTS_DIR, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())

        if not _starts_a_job_for_real(tree):
            continue

        if _replaces_the_starter(tree) or _names_the_door(tree):
            continue

        found[name] = "작업을 시작하고 기다리지 않는다"

    return found


class TheScannerReadsCallsNotWordsTest(unittest.TestCase):
    """세는 자가 틀리면 나머지 판정도 전부 틀린다."""

    def read(self, said):
        return ast.parse(said)

    def test_it_catches_a_direct_start(self):
        self.assertTrue(_starts_a_job_for_real(
            self.read("studio_jobs.start('주제')")))

    def test_it_catches_the_route(self):
        self.assertTrue(_starts_a_job_for_real(
            self.read("self.client.post('/studio/api/jobs', json=body)")))

    def test_it_lets_another_endpoint_pass(self):
        self.assertFalse(_starts_a_job_for_real(
            self.read("self.client.post('/studio/api/script-check')")))

    def test_it_sees_a_replaced_starter(self):
        self.assertTrue(_replaces_the_starter(
            self.read("patch('app.services.studio_jobs.start')")))
        self.assertTrue(_replaces_the_starter(
            self.read("patch.object(studio_jobs, 'start')")))

    def test_it_does_not_see_an_unrelated_patch(self):
        self.assertFalse(_replaces_the_starter(
            self.read("patch('app.services.image_service.generate_image')")))

    def test_it_sees_the_door(self):
        self.assertTrue(_names_the_door(
            self.read("studio_jobs.settle(timeout=5)")))

    def test_a_comment_about_the_door_is_not_the_door(self):
        """
        소스를 글자로 훑던 검사가 제 설명 주석에 걸린 적이 여러 번이다.
        """

        self.assertFalse(_names_the_door(
            self.read("# studio_jobs.settle() 을 불러야 한다\nx = 1\n")))


class NoTestLeavesAJobRunningTest(unittest.TestCase):
    """
    전수. 새로 늘어나면 여기서 걸린다.

    한 번 고치는 것으로는 부족하다 - 다음에 누가 작업을 시작하면서
    치우지 않으면, 그때는 아무도 모르고 회귀만 흔들린다.
    """

    def test_no_file_starts_a_job_without_the_door(self):
        """글로 본다 - 시작하는 자리와 치우는 자리가 같은 파일에 있는가."""

        self.assertEqual(_left_open(), {})

    def test_nothing_is_actually_running_right_now(self):
        """
        실제로 본다.

        시험과 시험 사이에는 도는 작업이 없어야 한다 - 있다면 앞선
        어떤 시험이 시작해 놓고 나간 것이다. 무엇이 남았는지까지
        말한다. "무언가 남았다"만으로는 누구를 고쳐야 하는지 모른다.
        """

        left = studio_jobs.running()

        said = []

        for job_id in left:
            found = studio_jobs.status(job_id)
            said.append("%s kind=%s state=%s topic=%s project=%s" % (
                job_id, found.get("kind"), found.get("state"),
                found.get("topic"), found.get("project_id")))

        self.assertEqual(
            left, [],
            "앞선 시험이 작업을 남기고 나갔습니다: " + " / ".join(said))


if __name__ == "__main__":
    unittest.main()
