"""
Sprint175 - 베타 사용자가 어디에서 멈추는지 안다 (Epic 58, Phase 7).

한 명이 써 보고 "잘 안 되던데요"라고 하면 우리가 할 수 있는 것이
없다. 어디까지 갔다가 멈췄는지를 알아야 한다.

무엇을 적지 않는가부터 정한다
-----------------------------
    사람 이름     적지 않는다
    파일 경로     적지 않는다
    영상 내용     적지 않는다
    대본 내용     적지 않는다

관찰은 사람을 들여다보는 일이 되기 쉽다. 그래서 "무엇을 적을까"가
아니라 "무엇은 절대 적지 않는가"를 먼저 못으로 박고, 그 다음에 그
울타리 안에서만 적는다.

적는 것은 셋뿐이다
------------------
    언제 켰는가        first/last/count
    어디까지 갔는가    정해 둔 이름의 사건들
    무엇에 걸렸는가    오류의 '종류'만. 원문은 적지 않는다

오류 원문은 이미 logs/에 있다(Sprint170). 그것은 사람이 제 손으로
보내 주는 것이고, 여기 있는 것은 화면이 보여 주는 요약이다. 둘을
섞지 않는다.
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
from app.services import beta_telemetry

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)

    def stored(self) -> dict:
        with open(beta_telemetry.path(), encoding="utf-8") as f:
            return json.load(f)


class LaunchTest(Base):
    """1. 첫 실행 상태."""

    def test_the_first_launch_is_recorded(self):
        self.assertFalse(os.path.exists(beta_telemetry.path()))

        found = beta_telemetry.launched()

        self.assertEqual(found["launch_count"], 1)
        self.assertTrue(found["first_launch_at"])
        self.assertEqual(found["last_launch_at"], found["first_launch_at"])

        # 적힌 것과 돌려준 것이 같다.
        self.assertEqual(self.stored()["launch_count"], 1)

    def test_the_second_launch_adds_up(self):
        first = beta_telemetry.launched()["first_launch_at"]

        second = beta_telemetry.launched()

        self.assertEqual(second["launch_count"], 2)

        # 처음 켠 때는 바뀌지 않는다 - 그것이 "언제부터 쓰기
        # 시작했는가"이기 때문이다.
        self.assertEqual(second["first_launch_at"], first)

        third = beta_telemetry.launched()

        self.assertEqual(third["launch_count"], 3)

    def test_a_broken_file_does_not_stop_the_program(self):
        """
        기록이 깨져 있어도 켜진다.

        관찰이 제품을 멈추게 하면 안 된다 - 관찰은 곁다리다.
        """

        runtime_paths.ensure(runtime_paths.dataset_root())

        with open(beta_telemetry.path(), "w", encoding="utf-8") as f:
            f.write("{ 이건 기록이 아니다")

        found = beta_telemetry.launched()

        self.assertEqual(found["launch_count"], 1)


class EventTest(Base):
    """2. 어디까지 갔는가."""

    def test_it_records_the_declared_events(self):
        for name in beta_telemetry.EVENTS:
            with self.subTest(name=name):
                beta_telemetry.record(name)

        events = self.stored()["events"]

        self.assertEqual([e["event"] for e in events],
                         list(beta_telemetry.EVENTS))

        for entry in events:
            with self.subTest(entry=entry["event"]):
                self.assertEqual(sorted(entry),
                                 ["event", "timestamp", "version"])
                self.assertEqual(entry["version"], app_info.VERSION)
                self.assertTrue(entry["timestamp"])

    def test_an_unknown_event_is_refused(self):
        """
        정해 둔 이름만 적는다.

        부르는 쪽이 아무 글자나 넣을 수 있으면, 그 글자에 무엇이 섞여
        들어올지 우리가 알 수 없다 - 개인정보를 막는 울타리가 거기서
        뚫린다.
        """

        with self.assertRaises(ValueError):
            beta_telemetry.record("사용자가 무릎 영상을 만들었다")

        self.assertFalse(os.path.exists(beta_telemetry.path()))

    def test_the_same_thing_is_not_counted_twice(self):
        """
        화면은 같은 것을 여러 번 물어본다.

        렌더가 끝났는지 1초마다 물어보므로, 물어볼 때마다 적으면
        기록이 그 한 번으로 뒤덮인다.
        """

        for _ in range(5):
            beta_telemetry.record(beta_telemetry.RENDER_COMPLETED,
                                  once="어떤 작업")

        self.assertEqual(len(self.stored()["events"]), 1)

        beta_telemetry.record(beta_telemetry.RENDER_COMPLETED,
                              once="다른 작업")

        self.assertEqual(len(self.stored()["events"]), 2)

    def test_what_makes_it_unique_is_not_kept_as_it_is(self):
        """
        같은 것인지 가리는 표는 그대로 적지 않는다.

        부르는 쪽이 무엇을 표로 줄지 우리가 다 알 수 없다. 그대로
        적어 두면 언젠가 경로나 제목이 그 자리에 들어온다.
        """

        beta_telemetry.record(beta_telemetry.RENDER_STARTED,
                              once=r"C:\Users\사람\내 영상\무릎.mp4")

        body = json.dumps(self.stored(), ensure_ascii=False)

        self.assertNotIn("무릎", body)
        self.assertNotIn("사람", body)

    def test_it_does_not_grow_without_end(self):
        for number in range(beta_telemetry.MAX_EVENTS + 30):
            beta_telemetry.record(beta_telemetry.RENDER_STARTED,
                                  once=str(number))

        events = self.stored()["events"]

        self.assertEqual(len(events), beta_telemetry.MAX_EVENTS)

        # 오래된 것부터 버린다 - 마지막에 무슨 일이 있었는지가 궁금하다.
        self.assertEqual(len(self.stored()["seen"]),
                         beta_telemetry.MAX_EVENTS)


class ErrorTest(Base):
    """3. 오류 요약."""

    def test_it_keeps_the_kind_and_the_time_only(self):
        beta_telemetry.failed(FileNotFoundError("C:\\사람\\내 자료 없음"))

        found = self.stored()

        self.assertEqual(found["last_error_kind"], "FileNotFoundError")
        self.assertTrue(found["last_error_time"])

        # 원문은 어디에도 없다.
        body = json.dumps(found, ensure_ascii=False)

        self.assertNotIn("내 자료 없음", body)
        self.assertNotIn("사람", body)
        self.assertNotIn("Traceback", body)

    def test_a_plain_name_also_works(self):
        """부르는 쪽이 예외가 아니라 이름만 알 때도 있다."""

        beta_telemetry.failed("bgm_missing")

        self.assertEqual(self.stored()["last_error_kind"], "bgm_missing")

    def test_the_kind_is_trimmed_so_nothing_leaks_in(self):
        """
        종류라는 이름으로 문장이 들어오지 않게 한다.

        부르는 쪽이 실수로 메시지를 통째로 넘길 수 있다.
        """

        beta_telemetry.failed("경로 C:\\Users\\사람\\x.png 를 못 읽음")

        kind = self.stored()["last_error_kind"]

        self.assertNotIn("\\", kind)
        self.assertNotIn("사람", kind)
        self.assertLessEqual(len(kind), beta_telemetry.MAX_KIND)


class PrivacyTest(Base):
    """무엇은 절대 적지 않는가."""

    def test_no_personal_fields_are_stored(self):
        """
        적어 둔 파일에 사람의 것이 하나도 없다.

        열쇠 이름도, 값도 본다 - 우리가 정한 열쇠 밖의 것은 아예
        없어야 한다.
        """

        beta_telemetry.launched()

        for name in beta_telemetry.EVENTS:
            beta_telemetry.record(name, once=name)

        beta_telemetry.failed(RuntimeError("무엇인가"))

        found = self.stored()

        self.assertEqual(sorted(found), sorted(beta_telemetry.KEYS))

        body = json.dumps(found, ensure_ascii=False)

        # 사람의 자리도, 이름도, 대본도 없다.
        for leak in (self.home, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME",
                     "무릎", ".png", ".mp4", "C:\\"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

    def test_it_lives_in_the_user_area_only(self):
        """
        사용자 자리의 관측 기록 폴더에만 쌓인다.

        사용자 자리 바로 아래에 두었더니, 개발 중에는 그 자리가
        저장소라서 뿌리에 파일이 떨어졌다 - 프로그램 폴더를 더럽히지
        않겠다던 말과 어긋난다.
        """

        beta_telemetry.launched()

        self.assertTrue(beta_telemetry.path().startswith(self.home))
        self.assertEqual(os.path.dirname(beta_telemetry.path()),
                         runtime_paths.dataset_root())

        # 저장소 뿌리에는 아무것도 안 생긴다 - 자리를 주지 않은 채로
        # 불러도 그렇다.
        self.assertFalse(os.path.exists(
            os.path.join(REPO, beta_telemetry.FILENAME)))

    def test_recording_never_breaks_the_product(self):
        """
        적지 못해도 하던 일은 그대로 간다.

        관찰이 제품을 멈추게 하면, 관찰을 켠 것이 잘못이 된다.
        """

        with patch.object(beta_telemetry, "_save",
                          side_effect=OSError("못 쓴다")):

            self.assertIsNone(
                beta_telemetry.note(beta_telemetry.RENDER_STARTED))
            self.assertIsNone(beta_telemetry.note_failure("무엇인가"))

    def test_note_still_refuses_unknown_events(self):
        """
        조용히 넘기는 것은 '쓰지 못한 것'뿐이다.

        모르는 이름은 부르는 쪽의 잘못이고, 그것까지 삼키면 울타리가
        있으나 마나가 된다.
        """

        with self.assertRaises(ValueError):
            beta_telemetry.note("아무 글자나")


class SummaryTest(Base):
    """4. 화면이 보여 줄 것."""

    def test_the_summary_says_what_the_file_says(self):
        beta_telemetry.launched()
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.RENDER_COMPLETED)

        found = beta_telemetry.summary()
        stored = self.stored()

        self.assertEqual(found["launch_count"], stored["launch_count"])
        self.assertEqual(found["last_launch_at"], stored["last_launch_at"])
        self.assertEqual(found["last_event"],
                         beta_telemetry.RENDER_COMPLETED)
        self.assertIsNone(found["last_error_kind"])

    def test_a_fresh_install_says_nothing_happened(self):
        found = beta_telemetry.summary()

        self.assertEqual(found["launch_count"], 0)
        self.assertIsNone(found["last_event"])
        self.assertIsNone(found["last_launch_at"])

    def test_the_report_carries_no_personal_data(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.OUTPUT_CHECK_FAILED)
        beta_telemetry.failed(FileNotFoundError("C:\\사람\\없다.png"))

        text = beta_telemetry.report()

        self.assertIn(app_info.VERSION, text)
        self.assertIn(beta_telemetry.OUTPUT_CHECK_FAILED, text)
        self.assertIn("FileNotFoundError", text)

        for leak in (self.home, "사람", "없다.png", "C:\\"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, text)


class ScreenTest(Base):
    """화면이 서버가 말한 것을 그대로 보여 준다."""

    def _about(self):
        from fastapi.testclient import TestClient

        from app.main import app

        answer = TestClient(app).get("/studio/api/about")

        self.assertEqual(answer.status_code, 200)

        return answer.json()

    def test_the_screen_and_the_server_agree(self):
        beta_telemetry.launched()
        beta_telemetry.record(beta_telemetry.PREPARATION_READY)

        found = self._about()["usage"]

        self.assertEqual(found, beta_telemetry.summary())

    def test_the_screen_has_the_place_and_the_button(self):
        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        self.assertIn("사용 기록", page)
        self.assertIn("사용 기록 복사", page)
        self.assertIn("/studio/api/about", page)

    def test_the_copied_text_comes_from_the_server(self):
        """
        붙여 넣을 글은 서버가 짓는다.

        화면이 제 나름대로 조립하면 사람마다 다른 모양이 오고, 그때
        무엇이 빠졌는지 우리가 알 수 없다 - Sprint174에서 정한 그
        규칙을 여기서도 따른다.
        """

        beta_telemetry.launched()

        self.assertEqual(self._about()["usage_report"],
                         beta_telemetry.report())


if __name__ == "__main__":
    unittest.main()
