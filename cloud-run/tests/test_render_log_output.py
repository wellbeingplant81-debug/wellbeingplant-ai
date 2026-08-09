"""
Sprint197 - 남의 프로그램이 한 말을 우리 화면에 그대로 쏟지 않는다.

그 print는 화면으로 간다
------------------------
studio_jobs._Tee가 sys.stdout을 가로채 job["console"]에 쌓고, 화면은
그것을 Console 패널에 보여 준다. 즉 렌더 중의 print는 사용자가 보는
글이다.

    print(result.stderr)
      -> _Tee.write -> job["console"] (상한 400줄)
      -> GET /studio/api/jobs/{id} -> studio.html

ffmpeg는 한 번 부를 때 26~55줄을 낸다. 세 자리가 렌더마다 한 번씩
부르므로 약 116줄, 상한의 29%다. 파이프라인이 남긴 진짜 진행 메시지가
그만큼 밀려난다 - 로그가 사라지는 원인이 이 print 자신이다.

그리고 그 줄에는 경로가 들어 있다
---------------------------------
    Input #0, concat, from 'C:\\Users\\...\\list.txt':

이 저장소는 이미 이것을 문제로 본다. beta_render_events.crashed()에
"종류만 적는다 - 메시지에는 경로가 들어 있다"고 적혀 있다. 기록에는
종류만 남기면서 화면에는 경로를 그대로 찍고 있었다.

실패 이유는 여기서 지켜지는 것이 아니다
---------------------------------------
print를 없애도 남는다. raise Exception(result.stderr)가 나르고,
studio_jobs가 그것을 console과 job["error"]에 적는다. print는 같은
것을 한 번 더, 그것도 성공했을 때까지 찍을 뿐이다.

그래서 이 파일은 두 가지를 함께 본다 - 화면이 조용해졌는가, 그리고
실패 이유는 그대로인가.
"""

import ast
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import audio_service, final_video_service, studio_jobs

CLOUD_RUN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WATCHED = (
    "app/services/audio_service.py",
    "app/services/final_video_service.py",
)

# 실제로 찍히던 모양 그대로. 배너 세 줄과 경로 한 줄, 그리고 오류.
HOME = os.path.expanduser("~")

BANNER = (
    "ffmpeg version 7.1-essentials_build-www.gyan.dev Copyright (c) 2000-2024\n"
    "  built with gcc 14.2.0 (Rev1, Built by MSYS2 project)\n"
    "  configuration: --enable-gpl --enable-version3 --enable-static\n"
    f"Input #0, concat, from '{os.path.join(HOME, 'scene_audio_list.txt')}':\n"
    "  Duration: 00:00:02.00, start: 0.000000, bitrate: 384 kb/s\n"
)

FAILED = BANNER + (
    f"Error opening input file {os.path.join(HOME, '없다.wav')}.\n"
    "Error opening input files: No such file or directory\n"
)


def _fake_ffmpeg(returncode=0, stderr=BANNER):
    return MagicMock(returncode=returncode, stdout="", stderr=stderr)


class ConsoleTest(unittest.TestCase):
    """진짜 Console 경로로 흘려 본다."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def console_of(self, work):
        """
        work()가 도는 동안 job["console"]에 쌓인 줄을 돌려준다.

        studio_jobs가 실제로 쓰는 그 _Tee를 그대로 쓴다 - 여기서
        흉내 내면 화면에 무엇이 뜨는지가 아니라 우리 흉내가 맞는지를
        재게 된다.
        """

        job_id = "sprint197"

        studio_jobs._jobs[job_id] = studio_jobs._new_job(
            job_id, "무릎 통증 완화", "wellbeing")
        self.addCleanup(studio_jobs._jobs.pop, job_id, None)

        original = sys.stdout
        sys.stdout = studio_jobs._Tee(io.StringIO(), job_id)

        try:
            work()
        finally:
            sys.stdout = original

        return list(studio_jobs._jobs[job_id]["console"])

    def test_joining_scene_audio_says_nothing(self):
        target = os.path.join(self.home, "voice.wav")

        with patch.object(audio_service.subprocess, "run",
                          return_value=_fake_ffmpeg()):
            said = self.console_of(
                lambda: audio_service.concat_scene_audio(
                    [os.path.join(self.home, "scene1.wav")], target))

        self.assertEqual(said, [])

    def test_making_the_final_video_says_nothing(self):
        with patch.object(final_video_service.subprocess, "run",
                          return_value=_fake_ffmpeg()):
            said = self.console_of(
                lambda: final_video_service.merge_video_audio(self.home))

        self.assertEqual(said, [])

    def test_no_absolute_path_reaches_the_screen(self):
        """
        찍히던 줄에는 사용자 이름이 든 경로가 있었다.
        """

        target = os.path.join(self.home, "voice.wav")

        with patch.object(audio_service.subprocess, "run",
                          return_value=_fake_ffmpeg()):
            said = "\n".join(self.console_of(
                lambda: audio_service.concat_scene_audio(
                    [os.path.join(self.home, "scene1.wav")], target)))

        for leak in (HOME, os.environ.get("USERNAME") or "USERNAME"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, said)

        self.assertNotIn("ffmpeg version", said)


class TheReasonSurvivesTest(unittest.TestCase):
    """실패 이유는 예외가 나른다. 그 길은 건드리지 않았다."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def test_joining_scene_audio_still_says_why(self):
        target = os.path.join(self.home, "voice.wav")

        with patch.object(audio_service.subprocess, "run",
                          return_value=_fake_ffmpeg(1, FAILED)):

            with self.assertRaises(Exception) as caught:
                audio_service.concat_scene_audio(
                    [os.path.join(self.home, "scene1.wav")], target)

        self.assertIs(type(caught.exception), Exception)
        self.assertIn("Error opening input file", str(caught.exception))

    def test_the_final_video_still_says_why(self):
        with patch.object(final_video_service.subprocess, "run",
                          return_value=_fake_ffmpeg(1, FAILED)):

            with self.assertRaises(Exception) as caught:
                final_video_service.merge_video_audio(self.home)

        self.assertIs(type(caught.exception), Exception)
        self.assertIn("Error opening input file", str(caught.exception))

    def test_what_ffmpeg_said_is_not_thrown_away(self):
        """
        화면에 안 보인다고 없앤 것은 아니다. 레벨을 올리면 돌아온다.
        """

        target = os.path.join(self.home, "voice.wav")

        with patch.object(audio_service.subprocess, "run",
                          return_value=_fake_ffmpeg()), \
                patch.object(audio_service.logger, "debug") as noted:

            audio_service.concat_scene_audio(
                [os.path.join(self.home, "scene1.wav")], target)

        self.assertTrue(noted.called, "ffmpeg가 한 말을 아무 데도 안 남겼습니다")


def _prints_a_child_stream(node) -> bool:
    """print(result.stdout) 같은 호출인가. 소스를 글자로 훑지 않는다."""

    if not (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"):
        return False

    for arg in node.args:
        for inner in ast.walk(arg):
            if (isinstance(inner, ast.Attribute)
                    and inner.attr in ("stdout", "stderr")):
                return True

    return False


class ThePrintPathDoesNotComeBackTest(unittest.TestCase):
    """
    다시 생기면 여기서 걸린다.

    한 번 지우는 것으로는 부족하다. 다음에 누가 디버깅하다가 print를
    되살리면 화면이 다시 더러워지고, 그때는 아무도 모른다.
    """

    def found_in(self, where: str) -> int:
        with open(os.path.join(CLOUD_RUN_DIR, where), encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return sum(1 for node in ast.walk(tree)
                   if _prints_a_child_stream(node))

    def test_the_watched_files_print_nothing_from_a_child(self):
        for where in WATCHED:
            with self.subTest(where=where):
                self.assertEqual(
                    self.found_in(where), 0,
                    f"{where}가 자식의 출력을 화면에 찍고 있습니다")

    def test_nowhere_else_in_app_either(self):
        left = {}

        for folder, dirs, files in os.walk(os.path.join(CLOUD_RUN_DIR, "app")):
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            for name in sorted(files):
                if not name.endswith(".py"):
                    continue

                where = os.path.relpath(
                    os.path.join(folder, name), CLOUD_RUN_DIR)
                count = self.found_in(where.replace("\\", "/"))

                if count:
                    left[where.replace("\\", "/")] = count

        self.assertEqual(left, {})

    def test_the_scanner_reads_calls_not_words(self):
        """
        소스를 문자열로 훑던 검사가 제 설명 주석에 걸린 적이 있다.
        """

        caught = [node for node in ast.walk(ast.parse(
            "# print(result.stderr)\nprint(result.stderr)\nprint('안녕')\n"))
            if _prints_a_child_stream(node)]

        self.assertEqual(len(caught), 1)


if __name__ == "__main__":
    unittest.main()
