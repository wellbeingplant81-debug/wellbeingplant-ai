"""
Sprint176 - 만든 쪽이 직접 적는다 (Epic 58, Phase 8).

Sprint175는 화면이 job을 물어볼 때 결과를 적었다. 아무도 물어보지
않으면 아무것도 안 적혔다 - 창을 닫아 두고 기다린 사람의 렌더는
기록에 없다. 우리가 알고 싶은 것이 정확히 그 사람이다.

그래서 만드는 실이 끝나는 자리에서 직접 적는다
----------------------------------------------
    시작했다   실이 시작할 때 한 번
    끝났다     결과 파일을 눈으로 본 다음에
    죽었다     예외로 끝났을 때

둘째가 중요하다. 엔진이 "됐다"고 해도 파일이 없으면 그 사람에게는
안 된 것이다. 그것을 completed로 적으면 되는 척이다.

무엇을 적지 않는가는 그대로다
-----------------------------
mp4 경로도, 프로젝트 id도, traceback도 적지 않는다. 파일이 있는지는
'보기만' 한다 - 보는 것과 적는 것은 다르다.
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
from app.services import beta_render_events, beta_telemetry, output_check


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)

        self.project = os.path.join(self.home, "output", "20260809_120000")
        os.makedirs(self.project)

    def _video(self):
        path = os.path.join(self.project, *output_check.VIDEO_RELATIVE)

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as f:
            f.write(b"0" * 2048)

        return path

    def events(self):
        return [e["event"] for e in self.stored()["events"]]

    def stored(self):
        with open(beta_telemetry.path(), encoding="utf-8") as f:
            return json.load(f)


class StartTest(Base):
    """1. 시작 시 1회."""

    def test_it_records_the_start(self):
        beta_render_events.started()

        self.assertEqual(self.events(), [beta_telemetry.RENDER_STARTED])

    def test_two_renders_are_two_starts(self):
        """
        같은 것을 두 번 적지 않는 규칙은 여기 없다.

        만드는 실은 한 번 돌고 끝난다 - 화면처럼 같은 자리를 여러 번
        지나지 않으므로, 두 번 적혔다면 정말 두 번 돈 것이다.
        """

        beta_render_events.started()
        beta_render_events.started()

        self.assertEqual(self.events(),
                         [beta_telemetry.RENDER_STARTED] * 2)


class FinishTest(Base):
    """2. 결과 파일을 본 다음에."""

    def test_a_made_video_is_a_completion(self):
        self._video()

        beta_render_events.finished(self.project)

        self.assertEqual(self.events(), [beta_telemetry.RENDER_COMPLETED])

    def test_no_file_is_not_a_completion(self):
        """
        엔진이 "됐다"고 해도 파일이 없으면 된 것이 아니다.

        그 사람은 영상을 받지 못했다. completed로 적으면 우리는
        "잘 됐네요"라고 답하게 된다.
        """

        beta_render_events.finished(self.project)

        self.assertEqual(self.events(), [beta_telemetry.RENDER_FAILED])
        self.assertEqual(self.stored()["last_error_kind"],
                         beta_render_events.NO_OUTPUT)

    def test_an_empty_file_is_not_a_video(self):
        """0바이트 파일은 있는 것이 아니다."""

        path = self._video()

        with open(path, "wb"):
            pass

        beta_render_events.finished(self.project)

        self.assertEqual(self.events(), [beta_telemetry.RENDER_FAILED])

    def test_it_looks_where_the_engine_puts_it(self):
        """
        보는 자리를 여기서 새로 정하지 않는다.

        두 자리가 따로 정해지면 만든 것을 못 찾는다 - 이 저장소가
        ffmpeg와 배경 음악에서 이미 두 번 겪었다.
        """

        self.assertTrue(beta_render_events.video_path(self.project)
                        .endswith(os.path.join(*output_check.VIDEO_RELATIVE)))

    def test_no_place_is_kept_even_when_it_is_there(self):
        """경로는 보기만 하고 적지 않는다."""

        self._video()

        beta_render_events.finished(self.project)

        body = json.dumps(self.stored(), ensure_ascii=False)

        self.assertNotIn(self.project, body)
        self.assertNotIn("20260809_120000", body)
        self.assertNotIn(".mp4", body)
        self.assertNotIn("output", body)


class CrashTest(Base):
    """3. 예외로 끝났을 때."""

    def test_an_exception_is_a_failure(self):
        beta_render_events.crashed(FileNotFoundError("C:\\사람\\없다.png"))

        self.assertEqual(self.events(), [beta_telemetry.RENDER_FAILED])
        self.assertEqual(self.stored()["last_error_kind"],
                         "FileNotFoundError")

    def test_the_message_and_the_traceback_are_not_kept(self):
        try:
            raise RuntimeError(r"C:\Users\사람\내 영상\무릎.mp4 를 못 만듦")
        except RuntimeError as failed:
            beta_render_events.crashed(failed)

        body = json.dumps(self.stored(), ensure_ascii=False)

        for leak in ("무릎", "사람", "Traceback", ".mp4", "C:\\"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)


class NeverBreaksTest(Base):
    """적는 일이 만드는 일을 멈추게 하지 않는다."""

    def test_a_broken_store_does_not_raise(self):
        with patch.object(beta_telemetry, "_save",
                          side_effect=OSError("못 쓴다")):

            self.assertIsNone(beta_render_events.started())
            self.assertIsNone(beta_render_events.finished(self.project))
            self.assertIsNone(beta_render_events.crashed(ValueError("x")))

    def test_a_missing_place_does_not_raise(self):
        self.assertIsNone(beta_render_events.finished(None))
        self.assertIsNone(beta_render_events.finished("C:\\없는곳\\없다"))


class WiringTest(Base):
    """만드는 실이 실제로 이것을 부른다."""

    def _run_job(self, outcome):
        """
        studio_jobs가 만드는 실을 그대로 돌린다.

        엔진은 부르지 않는다 - 이번 스프린트가 그쪽을 손대지 말라고
        했고, 여기서 보려는 것은 "끝났을 때 적히는가"뿐이다.
        """

        from app.services import studio_jobs

        with patch("app.services.factory_service.generate_short_video",
                   outcome):
            studio_jobs._run("작업1", "주제", "wellbeing", "20260809_120000")

        return studio_jobs.status("작업1")

    def setUp(self):
        super().setUp()

        from app.services import studio_jobs

        studio_jobs.reset()
        self.addCleanup(studio_jobs.reset)

        with studio_jobs._lock:
            studio_jobs._jobs["작업1"] = studio_jobs._new_job(
                "작업1", "주제", "wellbeing", "20260809_120000")

    def test_a_finished_render_is_recorded_without_anyone_looking(self):
        """
        화면을 열지 않아도 적힌다.

        Sprint175는 화면이 물어볼 때만 적었다. 여기서는 아무도
        물어보지 않는다 - status()조차 부르지 않는다.
        """

        self._video()

        def made(**kwargs):
            # 엔진이 실제로 돌려주는 모양. 자리를 제 입으로 알려 준다.
            return {"project_id": "20260809_120000", "title": "t",
                    "output": self.project}

        self._run_job(made)

        self.assertEqual(
            self.events(),
            [beta_telemetry.RENDER_STARTED, beta_telemetry.RENDER_COMPLETED])

    def test_a_crashed_render_is_recorded(self):
        def blows_up(**kwargs):
            raise RuntimeError("엔진이 죽었다")

        state = self._run_job(blows_up)

        self.assertEqual(state["state"], "failed")
        self.assertEqual(
            self.events(),
            [beta_telemetry.RENDER_STARTED, beta_telemetry.RENDER_FAILED])
        self.assertEqual(self.stored()["last_error_kind"], "RuntimeError")

    def test_the_screen_no_longer_writes_the_result(self):
        """
        같은 일을 두 자리가 적지 않는다.

        만드는 쪽이 적기 시작했으므로 화면 쪽 기록은 걷어냈다 - 두
        자리가 적으면 한 번 돈 렌더가 두 번으로 보인다.
        """

        source = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "routers", "studio.py")

        with open(source, encoding="utf-8") as f:
            body = f.read()

        import re

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for gone in ("RENDER_COMPLETED", "RENDER_FAILED", "RENDER_STARTED"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, code)

    def test_the_stored_shape_is_unchanged(self):
        """
        적히는 모양은 Sprint175 그대로다.

        받아 보는 쪽(화면·복사 글)이 예전 그대로 읽을 수 있어야 한다.
        """

        self._video()

        self._run_job(lambda **kwargs: {"project_id": "20260809_120000",
                                        "output": self.project})

        found = self.stored()

        self.assertEqual(sorted(found), sorted(beta_telemetry.KEYS))

        for entry in found["events"]:
            with self.subTest(entry=entry["event"]):
                self.assertEqual(sorted(entry),
                                 ["event", "timestamp", "version"])

        self.assertTrue(beta_telemetry.path().startswith(self.home))


if __name__ == "__main__":
    unittest.main()
