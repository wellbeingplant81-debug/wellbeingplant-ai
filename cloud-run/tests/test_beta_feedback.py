"""
Sprint177 - 보내온 것을 우리가 바로 읽을 수 있게 (Epic 58, Phase 9).

Sprint175·176이 "어디까지 갔는가"를 적기 시작했다. 그런데 그것을
사람이 우리에게 보내려면 지금은 파일을 찾아 열어서 통째로 붙여야
한다. 곤란해진 사람에게 그것까지 시키면 대개 안 보낸다.

그래서 보낼 것을 한 덩이로 만든다
---------------------------------
누르면 복사되고, 붙여넣으면 우리가 읽을 수 있는 글이다.

무엇을 담지 않는가가 먼저다
---------------------------
    파일 경로     프로젝트명     사용자명
    대본 내용     이미지 이름    영상 이름    mp4 위치

담지 않는 이유는 두 가지다. 하나는 남의 것이기 때문이고, 하나는
그것이 없어도 우리가 알아야 할 것은 다 알 수 있기 때문이다.

울타리는 이미 서 있다
---------------------
beta_telemetry가 애초에 그런 것을 적지 않는다. 여기서는 그 안에 있는
것만 옮긴다 - 새 자리에서 원본을 다시 읽어 오면 울타리 밖으로 나가는
길이 생긴다.
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
from app.services import beta_feedback, beta_telemetry

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)

    def _walked(self, *events):
        for name in events:
            beta_telemetry.record(name)


class PackageTest(Base):
    """1. 무엇을 담는가."""

    def test_it_carries_the_declared_fields(self):
        beta_telemetry.launched()
        self._walked(beta_telemetry.WORKSPACE_SELECTED,
                     beta_telemetry.SCRIPT_READY,
                     beta_telemetry.RENDER_COMPLETED)

        found = beta_feedback.package()

        self.assertEqual(sorted(found), sorted(beta_feedback.FIELDS))

        self.assertEqual(found["version"], beta_feedback.VERSION)
        self.assertEqual(found["app_version"], app_info.VERSION)
        self.assertTrue(found["created_at"])
        self.assertEqual(found["launch_count"], 1)
        self.assertEqual(found["last_event"],
                         beta_telemetry.RENDER_COMPLETED)
        self.assertIsNone(found["last_error_kind"])
        self.assertEqual(found["flow_summary"],
                         [beta_telemetry.WORKSPACE_SELECTED,
                          beta_telemetry.SCRIPT_READY,
                          beta_telemetry.RENDER_COMPLETED])

    def test_a_fresh_install_says_nothing_happened(self):
        found = beta_feedback.package()

        self.assertEqual(found["launch_count"], 0)
        self.assertIsNone(found["last_event"])
        self.assertEqual(found["flow_summary"], [])

    def test_the_flow_keeps_the_story_of_a_retry(self):
        """
        같은 이름이 다시 나오면 그대로 둔다.

        한 번 실패하고 다시 만든 사람과, 한 번에 된 사람은 다른
        사람이다. 이름이 같다고 합치면 그 차이가 사라진다.
        """

        self._walked(beta_telemetry.RENDER_STARTED,
                     beta_telemetry.RENDER_FAILED,
                     beta_telemetry.RENDER_STARTED,
                     beta_telemetry.RENDER_COMPLETED)

        self.assertEqual(beta_feedback.package()["flow_summary"],
                         [beta_telemetry.RENDER_STARTED,
                          beta_telemetry.RENDER_FAILED,
                          beta_telemetry.RENDER_STARTED,
                          beta_telemetry.RENDER_COMPLETED])

    def test_a_repeat_in_a_row_is_collapsed(self):
        """
        바로 잇달아 같은 것이 오면 한 번으로 본다.

        읽는 사람에게 같은 줄이 열 번 이어지는 것은 아무 말도 하지
        않는다 - 그 사이에 무엇이 있었는지가 이야기다.
        """

        for _ in range(5):
            beta_telemetry.record(beta_telemetry.PREPARATION_READY)

        self.assertEqual(beta_feedback.package()["flow_summary"],
                         [beta_telemetry.PREPARATION_READY])

    def test_the_flow_does_not_run_on_forever(self):
        for number in range(beta_feedback.MAX_FLOW + 20):
            beta_telemetry.record(
                beta_telemetry.RENDER_STARTED if number % 2
                else beta_telemetry.RENDER_COMPLETED)

        flow = beta_feedback.package()["flow_summary"]

        self.assertEqual(len(flow), beta_feedback.MAX_FLOW)

        # 마지막 것을 남긴다 - 사람이 방금 겪은 일이 그쪽에 있다.
        self.assertEqual(flow[-1], beta_telemetry.RENDER_STARTED)

    def test_it_only_carries_names_we_declared(self):
        """
        흐름에 들어가는 이름은 beta_telemetry가 정한 것뿐이다.

        여기서 원본을 다시 읽어 오면 울타리 밖으로 나가는 길이 생긴다.
        """

        self._walked(*beta_telemetry.EVENTS)

        for name in beta_feedback.package()["flow_summary"]:
            with self.subTest(name=name):
                self.assertIn(name, beta_telemetry.EVENTS)


class PrivacyTest(Base):
    """무엇을 담지 않는가."""

    def test_no_personal_data_anywhere(self):
        beta_telemetry.launched()
        self._walked(*beta_telemetry.EVENTS)
        beta_telemetry.failed(FileNotFoundError(
            r"C:\Users\사람\내 영상\무릎 스트레칭.png 없음"))

        body = json.dumps(beta_feedback.package(), ensure_ascii=False)
        text = beta_feedback.report()

        # "output"을 맨 문자열로 찾지 않는다 - 정해 둔 사건 이름
        # output_check_failed가 거기 걸린다. 우리가 막으려는 것은
        # 경로이므로 경로의 모양으로 본다.
        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME",
                     "무릎", "스트레칭", ".png", ".mp4", "C:\\",
                     "\\\\output\\\\", "/output/", "Traceback"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)
                self.assertNotIn(leak, text)

    def test_a_project_name_never_reaches_it(self):
        """
        프로젝트 이름은 애초에 적히지 않으므로 여기에도 없다.

        적히는 자리를 지나 왔는지 실제로 확인한다 - "없을 것이다"로
        두면 어느 날 누가 그 자리에 적기 시작한다.
        """

        beta_telemetry.record(beta_telemetry.SCRIPT_READY,
                              once="20260809_120000")

        body = json.dumps(beta_feedback.package(), ensure_ascii=False)

        self.assertNotIn("20260809_120000", body)

    def test_it_reads_only_what_was_already_stored(self):
        """
        원본을 새로 뒤지지 않는다.

        beta_telemetry가 내주는 것만 쓴다 - 그쪽이 울타리를 들고
        있으므로, 여기서 파일을 직접 열면 그 울타리를 우회하게 된다.
        """

        import re

        source = os.path.join(REPO, "app", "services", "beta_feedback.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for forbidden in ("open(", "os.walk", "listdir", "json.load"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)

    def test_nothing_is_written_anywhere(self):
        """
        만들기만 하고 적지 않는다.

        보낼 것을 만드는 일이 새 파일을 남기면, 그 파일이 또 어디에
        쌓이는지 설명해야 한다.
        """

        before = sorted(os.listdir(self.home)) if os.path.isdir(self.home) \
            else []

        beta_feedback.package()
        beta_feedback.report()

        after = sorted(os.listdir(self.home)) if os.path.isdir(self.home) \
            else []

        self.assertEqual(before, after)

        # 프로그램 자리에도 없다.
        self.assertFalse(os.path.exists(
            os.path.join(REPO, "beta_feedback.json")))


class ReportTest(Base):
    """사람이 붙여 넣을 글."""

    def test_it_reads_like_the_declared_shape(self):
        beta_telemetry.launched()
        self._walked(beta_telemetry.WORKSPACE_SELECTED,
                     beta_telemetry.SCRIPT_READY,
                     beta_telemetry.RENDER_COMPLETED)

        text = beta_feedback.report()

        self.assertTrue(text.startswith(f"{app_info.NAME} 베타 피드백"))

        for mark in ("버전:", "마지막 상태:", "최근 오류:", "사용 흐름:",
                     app_info.VERSION,
                     beta_telemetry.RENDER_COMPLETED,
                     beta_telemetry.WORKSPACE_SELECTED):
            with self.subTest(mark=mark):
                self.assertIn(mark, text)

    def test_no_error_says_so_plainly(self):
        beta_telemetry.launched()

        self.assertIn("없음", beta_feedback.report())

    def test_an_error_is_named(self):
        beta_telemetry.failed(RuntimeError("무엇인가"))

        self.assertIn("RuntimeError", beta_feedback.report())

    def test_nothing_yet_is_not_an_empty_hole(self):
        """
        아직 아무것도 안 한 사람의 글도 읽을 수 있어야 한다.

        빈 줄만 오면 받은 우리가 "이게 뭐지" 하게 된다.
        """

        text = beta_feedback.report()

        self.assertIn("아직", text)


class ApiTest(Base):
    """4. 서버가 내주는 것."""

    def _get(self):
        from fastapi.testclient import TestClient

        from app.main import app

        answer = TestClient(app).get("/studio/api/beta-feedback")

        self.assertEqual(answer.status_code, 200)

        return answer.json()

    def test_the_api_gives_the_package_and_the_text(self):
        beta_telemetry.launched()
        self._walked(beta_telemetry.WORKSPACE_SELECTED)

        found = self._get()

        for key in beta_feedback.FIELDS:
            with self.subTest(key=key):
                self.assertIn(key, found)

        self.assertEqual(found["report"], beta_feedback.report())

    def test_what_the_screen_copies_is_what_the_api_says(self):
        """
        붙여 넣을 글은 서버가 짓는다.

        화면이 제 나름대로 조립하면 받아 보는 글의 모양이 사람마다
        달라진다(Sprint174에서 정한 규칙).
        """

        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-feedback", page)
        self.assertIn("베타 피드백 복사", page)

    def test_the_screen_tells_what_to_send_before_asking(self):
        """
        문의처만 보여 주면 사람은 "안 돼요"라고만 보낸다.

        무엇을 함께 보내면 되는지를 묻기 전에 말한다.
        """

        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        self.assertIn("함께 보내주시면", page)
        self.assertIn(app_info.CONTACT, page)


if __name__ == "__main__":
    unittest.main()
