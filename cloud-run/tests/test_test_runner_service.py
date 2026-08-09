import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.test_runner_service import (
    CLOUD_RUN_DIR,
    decode_output,
    parse_unittest_summary,
    build_unittest_command,
    run_tests,
)

# Sprint194 - 진짜로 돌려 볼 작은 모듈들.
#
# discover의 기본 패턴은 test*.py 이므로 이 이름들은 전체 실행에
# 딸려 들어가지 않는다. 일부러 실패하는 것을 tests/에 남겨 두면
# regression이 영영 빨간색이 된다.

PROBE_PASSES = '''import unittest


class Probe(unittest.TestCase):

    def test_it_passes(self):
        self.assertEqual("대본 준비", "대본 준비")
'''

PROBE_MIXED = '''import sys
import unittest


class Probe(unittest.TestCase):

    def test_a_grandchild_writes_utf8_into_the_pipe(self):
        """ffmpeg가 하는 그대로 - 파이프에 UTF-8 바이트를 직접 쓴다."""

        sys.stdout.buffer.write(
            "[ffmpeg] 배경 음악을 입히는 중입니다\\n".encode("utf-8") * 200)
        sys.stdout.buffer.flush()

    def test_it_fails_in_korean(self):
        self.assertEqual("배경 음악이 없어 영상을 만들 수 없습니다",
                         "대본까지 간 기록 0벌")
'''


class TestParseUnittestSummary(unittest.TestCase):

    def test_parses_successful_run(self):
        output = (
            "test_a (tests.test_x.TestX) ... ok\n"
            "test_b (tests.test_x.TestX) ... ok\n"
            "\n"
            "----------------------------------------------------------------------\n"
            "Ran 638 tests in 5.743s\n"
            "\n"
            "OK\n"
        )

        summary = parse_unittest_summary(output)

        self.assertEqual(summary["ran"], 638)
        self.assertAlmostEqual(summary["seconds"], 5.743, places=3)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["failures"], 0)
        self.assertEqual(summary["errors"], 0)

    def test_parses_failed_run_with_failures_and_errors(self):
        output = (
            "Ran 10 tests in 1.234s\n"
            "\n"
            "FAILED (failures=2, errors=1)\n"
        )

        summary = parse_unittest_summary(output)

        self.assertEqual(summary["ran"], 10)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["failures"], 2)
        self.assertEqual(summary["errors"], 1)

    def test_parses_failed_run_with_only_failures(self):
        output = "Ran 5 tests in 0.100s\n\nFAILED (failures=3)\n"

        summary = parse_unittest_summary(output)

        self.assertEqual(summary["failures"], 3)
        self.assertEqual(summary["errors"], 0)
        self.assertFalse(summary["ok"])

    def test_missing_ran_line_defaults_to_zero_and_not_ok(self):
        summary = parse_unittest_summary("some unrelated crash output\n")

        self.assertEqual(summary["ran"], 0)
        self.assertFalse(summary["ok"])


class TestBuildUnittestCommand(unittest.TestCase):

    def test_no_modules_runs_full_discovery(self):
        command = build_unittest_command([])
        self.assertIn("discover", command)
        self.assertIn("-s", command)
        self.assertIn("tests", command)

    def test_specific_modules_are_passed_through(self):
        command = build_unittest_command(["tests.test_video_builder", "tests.test_bgm_service"])
        self.assertIn("tests.test_video_builder", command)
        self.assertIn("tests.test_bgm_service", command)
        self.assertNotIn("discover", command)

    def test_uses_project_venv_python(self):
        command = build_unittest_command([])
        self.assertIn("-m", command)
        self.assertIn("unittest", command)


class TestRunTests(unittest.TestCase):

    @patch("app.services.test_runner_service.subprocess.run")
    def test_run_tests_returns_parsed_summary(self, mock_run):
        # Sprint194 - 이제 바이트로 받는다. 글자로 받으면 읽는 스레드
        # 안에서 죽어 무엇이 실패했는지를 못 본다.
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"",
            stderr=b"Ran 3 tests in 0.01s\n\nOK\n",
        )

        result = run_tests(["tests.test_bgm_service"])

        self.assertTrue(result["summary"]["ok"])
        self.assertEqual(result["summary"]["ran"], 3)
        self.assertEqual(result["returncode"], 0)

    @patch("app.services.test_runner_service.subprocess.run")
    def test_run_tests_reports_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"Ran 3 tests in 0.01s\n\nFAILED (failures=1)\n",
        )

        result = run_tests(["tests.test_bgm_service"])

        self.assertFalse(result["summary"]["ok"])
        self.assertEqual(result["returncode"], 1)


class TestDecodeOutput(unittest.TestCase):
    """Sprint194 - 자식이 낸 바이트를 글로 바꾼다."""

    def test_utf8_korean_comes_back_whole(self):
        said = "배경 음악이 없어 영상을 만들 수 없습니다"

        self.assertEqual(decode_output(said.encode("utf-8")), said)

    def test_locale_korean_comes_back_whole(self):
        said = "대본까지 간 기록 0벌"

        self.assertEqual(decode_output(said.encode("cp949")), said)

    def test_both_at_once_come_back_whole(self):
        """
        한 스트림에 인코딩이 둘 섞이는 것이 이 결함의 본체다.

        자식 unittest는 로케일로 쓰는데, 파이프를 물려받은 손자
        (ffmpeg 같은 것)는 제 인코딩으로 쓴다.
        """

        mine = "무료 제작 흐름 - 대본까지 간 기록 0벌"
        theirs = "[ffmpeg] 배경 음악을 입히는 중입니다"

        raw = (theirs.encode("utf-8") + b"\n"
               + mine.encode("cp949") + b"\n"
               + theirs.encode("utf-8") + b"\n")

        found = decode_output(raw)

        self.assertIn(mine, found)
        self.assertIn(theirs, found)
        self.assertEqual(found.count(theirs), 2)

    def test_utf8_wins_when_a_line_could_be_read_either_way(self):
        """
        UTF-8 한글은 cp949로도 '읽히기는' 한다 - 엉뚱한 한자로.

        먼저 대 보는 쪽이 UTF-8이어야 각 줄이 제 주인에게 간다.
        """

        said = "판번호를 담아 답하는지만 봅니다"

        self.assertEqual(decode_output(said.encode("utf-8")), said)

    def test_a_byte_nobody_can_read_does_not_stop_the_rest(self):
        """
        여기서 예외를 내면 윗줄과 아랫줄까지 통째로 못 보게 된다.
        """

        raw = (b"Ran 3 tests in 0.01s\n"
               + b"\xff\xfe\x00\x01\n"
               + b"FAILED (failures=1)\n")

        found = decode_output(raw)

        self.assertIn("Ran 3 tests in 0.01s", found)
        self.assertIn("FAILED (failures=1)", found)

    def test_nothing_to_read_is_not_an_error(self):
        self.assertEqual(decode_output(b""), "")
        self.assertEqual(decode_output(None), "")


class TestRunTestsLeavesTheChildAlone(unittest.TestCase):
    """
    Sprint194 - 자식에게 "UTF-8로 말하라"고 시키지 않는다.

    그 지시는 손자에게까지 내려간다. 실제로 그렇게 만들었더니, 손자의
    말을 로케일로 읽고 있던 test_script_resolver가 대신 깨졌다. 고치려는
    것은 우리가 읽는 방식이지 자식이 도는 방식이 아니다.
    """

    @patch("app.services.test_runner_service.subprocess.run")
    def test_it_does_not_reach_into_the_child_environment(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"", stderr=b"Ran 1 test in 0.01s\n\nOK\n")

        run_tests(["tests.test_bgm_service"])

        asked = mock_run.call_args.kwargs

        self.assertIsNone(asked.get("env"))

        for gone in ("PYTHONIOENCODING", "PYTHONUTF8"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, str(asked.get("env")))

    @patch("app.services.test_runner_service.subprocess.run")
    def test_it_asks_for_bytes_not_text(self, mock_run):
        """
        text=True로 받으면 읽는 스레드 안에서 죽는다 - 우리가 손쓸 수
        없는 자리다.
        """

        mock_run.return_value = MagicMock(
            returncode=0, stdout=b"", stderr=b"Ran 1 test in 0.01s\n\nOK\n")

        run_tests(["tests.test_bgm_service"])

        asked = mock_run.call_args.kwargs

        self.assertFalse(asked.get("text"))
        self.assertIsNone(asked.get("encoding"))


class TestRunTestsForReal(unittest.TestCase):
    """
    Sprint194 - 진짜 프로세스를 돌려 본다.

    mock으로는 이 결함을 잡을 수 없다. 죽는 자리가 subprocess가 파이프를
    읽는 스레드 안이기 때문이다 - 그 스레드를 흉내 내면 결함도 같이
    사라진다.
    """

    def probe(self, label, body):
        """tests/ 안에 잠깐 두었다가 지운다."""

        name = f"_sprint194_probe_{os.getpid()}_{label}"
        path = os.path.join(CLOUD_RUN_DIR, "tests", f"{name}.py")

        with open(path, "w", encoding="utf-8") as f:
            f.write(body)

        self.addCleanup(self.forget, path)

        return f"tests.{name}"

    def forget(self, path):
        for target in (path, path + "c"):
            if os.path.exists(target):
                os.remove(target)

        cache = os.path.join(os.path.dirname(path), "__pycache__")
        stem = os.path.basename(path)[:-3]

        if os.path.isdir(cache):
            for left in os.listdir(cache):
                if left.startswith(stem + "."):
                    os.remove(os.path.join(cache, left))

    def test_a_passing_module_still_reports_ok(self):
        """고친 뒤에도 평소 실행은 그대로여야 한다."""

        found = run_tests([self.probe("passes", PROBE_PASSES)])

        self.assertTrue(found["summary"]["ok"])
        self.assertEqual(found["summary"]["ran"], 1)
        self.assertEqual(found["summary"]["failures"], 0)
        self.assertEqual(found["summary"]["errors"], 0)
        self.assertEqual(found["returncode"], 0)

    def test_a_korean_failure_comes_back_whole(self):
        """
        한 스트림에 두 인코딩이 섞여도 러너가 죽지 않는다.

        Sprint192/193에서 이것 때문에 regression 결과를 두 번 못 봤다.
        읽는 스레드가 죽으면 stdout/stderr가 None이 되고, 정작 무엇이
        실패했는지를 볼 수 없다.
        """

        found = run_tests([self.probe("mixed", PROBE_MIXED)])

        self.assertEqual(found["summary"]["ran"], 2)
        self.assertEqual(found["summary"]["failures"], 1)
        self.assertFalse(found["summary"]["ok"])
        self.assertEqual(found["returncode"], 1)

        raw = found["raw_output"]

        for said in ("배경 음악이 없어 영상을 만들 수 없습니다",
                     "대본까지 간 기록 0벌",
                     "[ffmpeg] 배경 음악을 입히는 중입니다"):
            with self.subTest(said=said):
                self.assertIn(said, raw)

    def test_it_leaves_nothing_behind(self):
        folder = os.path.join(CLOUD_RUN_DIR, "tests")

        before = sorted(os.listdir(folder))

        run_tests([self.probe("tidy", PROBE_PASSES)])
        self.forget(os.path.join(folder,
                                 f"_sprint194_probe_{os.getpid()}_tidy.py"))

        self.assertEqual(sorted(os.listdir(folder)), before)


if __name__ == "__main__":
    unittest.main()
