"""
Sprint198 - 실패했을 때 화면에 뜨는 글에서 경로를 가린다.

Sprint197이 성공·실패 가리지 않고 상시로 찍히던 것을 없앴다면, 여기는
실패했을 때만 뜨는 것이다.

두 갈래로 나간다
----------------
    raise Exception(result.stderr)
      -> studio_jobs 의 except
      -> job["error"]            -> 화면 "실패: ..."
      -> _append_line(traceback) -> Console

실측으로 job["error"]에 절대 경로 2줄, Console에 7줄이었다. Console
쪽이 더 큰 이유는 traceback이다 - 프레임마다 프로젝트 절대 경로가
들어 있다.

던지는 자리는 건드리지 않는다
-----------------------------
예외를 던지는 곳은 audio_service·final_video_service·duration_optimizer
·asset_integration_service·elevenlabs_provider·voice_import 이고,
전부 Render Engine과 Provider다. 그래서 표시 경계에서만 가린다.

예외 객체 자체는 원문을 그대로 들고 있다. 로그와 터미널에서는 전체
경로를 볼 수 있고, 화면에만 가려진 글이 간다 - 보는 사람이 다르면
보이는 것도 달라야 한다.

_append_line에 걸면 안 된다
---------------------------
그 함수는 "Project : C:\\..." 한 줄에서 작업 디렉터리를 뽑아낸다.
먼저 가려 버리면 job["project_path"]가 태그가 되고 진행률 표시가
조용히 죽는다. 그래서 except 넷에만 명시적으로 건다. 이 파일의
마지막 테스트가 그것을 지킨다.
"""

import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import runtime_paths
from app.services import audio_service, factory_service, studio_jobs

DRIVE = re.compile(r"[A-Za-z]:[\\/]")

# 주제명이 폴더가 되는 그 모양. 공백과 한글이 함께 있다 - \S+ 로 끊는
# 정규식이 여기서 무너진다.
TOPIC = "무릎 통증 완화 스트레칭"


def _drive_lines(text):
    return [line for line in (text or "").splitlines() if DRIVE.search(line)]


class MaskTest(unittest.TestCase):
    """가리는 함수 자체. 순수 문자열이라 빠르게 여러 모양을 본다."""

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_the_user_home_goes_away(self):
        said = studio_jobs._masked(
            f"Error opening input file {os.path.expanduser('~')}\\a.wav")

        self.assertNotIn(os.path.expanduser("~"), said)
        self.assertNotIn(os.environ.get("USERNAME") or "USERNAME", said)

    def test_our_data_folder_goes_away(self):
        said = studio_jobs._masked(f"열 수 없습니다: {self.home}\\output\\x")

        self.assertNotIn(self.home, said)

    def test_the_program_folder_goes_away(self):
        said = studio_jobs._masked(
            f"File \"{runtime_paths.program_dir()}\\app\\x.py\", line 1")

        self.assertNotIn(runtime_paths.program_dir(), said)

    def test_a_korean_path_with_spaces_goes_away_whole(self):
        """
        \\S+ 로 끊으면 '무릎'까지만 지우고 나머지가 남는다.
        """

        path = os.path.join(os.path.expanduser("~"), TOPIC, "audio", "a.wav")

        said = studio_jobs._masked(f"Impossible to open '{path}'")

        for piece in ("무릎", "통증", "완화", "스트레칭"):
            with self.subTest(piece=piece):
                self.assertNotIn(piece, said)

    def test_the_file_name_stays(self):
        """가린 뒤에도 어느 파일인지는 알 수 있어야 한다."""

        path = os.path.join(os.path.expanduser("~"), TOPIC,
                            "scene_audio_list.txt")

        said = studio_jobs._masked(f"Error opening input file {path}")

        self.assertIn("scene_audio_list.txt", said)
        self.assertIn("Error opening input file", said)

    def test_a_line_without_any_path_is_untouched(self):
        said = "Invalid data found when processing input"

        self.assertEqual(studio_jobs._masked(said), said)

    def test_more_than_one_path_in_a_line(self):
        home = os.path.expanduser("~")

        said = studio_jobs._masked(
            f"copy {home}\\a.wav -> {home}\\{TOPIC}\\b.wav")

        self.assertEqual(_drive_lines(said), [])
        self.assertIn("a.wav", said)
        self.assertIn("b.wav", said)

    def test_nothing_to_mask_is_not_an_error(self):
        self.assertEqual(studio_jobs._masked(""), "")
        self.assertEqual(studio_jobs._masked(None), "")


class FailedJobTest(unittest.TestCase):
    """화면까지 가는 길 전체. studio_jobs._run을 그대로 통과시킨다."""

    def setUp(self):
        self.home = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

        self.work = os.path.join(self.home, TOPIC, "audio")
        os.makedirs(self.work, exist_ok=True)

        self.job_id = "sprint198"
        studio_jobs._jobs[self.job_id] = studio_jobs._new_job(
            self.job_id, TOPIC, "wellbeing")
        self.addCleanup(studio_jobs._jobs.pop, self.job_id, None)

    def ffmpeg_said(self):
        """실측에서 실제로 나온 그 모양."""

        listed = os.path.join(self.work, "scene_audio_list.txt")

        return (
            "ffmpeg version 7.1-essentials_build-www.gyan.dev\n"
            f"[concat @ 0000018e] Impossible to open "
            f"'{os.path.join(self.work, 'scene1.wav')}'\n"
            f"Error opening input file {listed}.\n"
            "Error opening input files: No such file or directory\n"
        )

    def run_and_fail(self):
        said = self.ffmpeg_said()

        def boom(**asked):
            with patch.object(
                    audio_service.subprocess, "run",
                    return_value=MagicMock(returncode=1, stdout="",
                                           stderr=said)):
                audio_service.concat_scene_audio(
                    [os.path.join(self.work, "scene1.wav")],
                    os.path.join(self.work, "voice.wav"))

        with patch.object(factory_service, "generate_short_video", boom):
            studio_jobs._run(self.job_id, TOPIC, "wellbeing", None)

        return studio_jobs._jobs[self.job_id]

    def test_the_home_path_does_not_reach_the_screen(self):
        job = self.run_and_fail()

        self.assertEqual(job["state"], "failed")

        for leak in (os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME", self.home):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, job["error"])

    def test_no_absolute_path_in_the_error(self):
        job = self.run_and_fail()

        self.assertEqual(_drive_lines(job["error"]), [])

    def test_no_absolute_path_in_the_console(self):
        """
        traceback이 여기로 온다. 프레임마다 프로젝트 경로가 들어 있다.
        """

        job = self.run_and_fail()

        self.assertEqual(_drive_lines("\n".join(job["console"])), [])

    def test_the_korean_folder_name_does_not_reach_the_screen(self):
        job = self.run_and_fail()

        whole = job["error"] + "\n".join(job["console"])

        for piece in ("무릎", "스트레칭"):
            with self.subTest(piece=piece):
                self.assertNotIn(piece, whole)

    def test_the_reason_is_still_readable(self):
        job = self.run_and_fail()

        self.assertIn("Error opening input file", job["error"])
        self.assertIn("scene_audio_list.txt", job["error"])
        self.assertIn("No such file or directory", job["error"])


class TheExceptionItselfIsUntouchedTest(unittest.TestCase):
    """
    던지는 쪽은 그대로다. 가리는 것은 화면으로 나갈 때뿐이다.
    """

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_the_raise_still_carries_the_real_path(self):
        said = f"Error opening input file {self.home}\\a.wav"

        with patch.object(audio_service.subprocess, "run",
                          return_value=MagicMock(returncode=1, stdout="",
                                                 stderr=said)):

            with self.assertRaises(Exception) as caught:
                audio_service.concat_scene_audio(
                    [os.path.join(self.home, "scene1.wav")],
                    os.path.join(self.home, "voice.wav"))

        self.assertIs(type(caught.exception), Exception)
        self.assertIn(self.home, str(caught.exception))


class ProjectLineStillWorksTest(unittest.TestCase):
    """
    5절의 함정. _append_line에 가리기를 걸면 여기가 조용히 죽는다.
    """

    def setUp(self):
        self.job_id = "sprint198project"
        studio_jobs._jobs[self.job_id] = studio_jobs._new_job(
            self.job_id, TOPIC, "wellbeing")
        self.addCleanup(studio_jobs._jobs.pop, self.job_id, None)

    def test_the_project_path_is_read_unmasked(self):
        real = os.path.join(os.path.expanduser("~"), "output", "20260810")

        studio_jobs._append_line(self.job_id, f"Project : {real}")

        self.assertEqual(
            studio_jobs._jobs[self.job_id]["project_path"], real)


if __name__ == "__main__":
    unittest.main()
