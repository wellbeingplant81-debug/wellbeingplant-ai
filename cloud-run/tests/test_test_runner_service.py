import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.test_runner_service import (
    parse_unittest_summary,
    build_unittest_command,
    run_tests,
)


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
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="Ran 3 tests in 0.01s\n\nOK\n",
        )

        result = run_tests(["tests.test_bgm_service"])

        self.assertTrue(result["summary"]["ok"])
        self.assertEqual(result["summary"]["ran"], 3)
        self.assertEqual(result["returncode"], 0)

    @patch("app.services.test_runner_service.subprocess.run")
    def test_run_tests_reports_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Ran 3 tests in 0.01s\n\nFAILED (failures=1)\n",
        )

        result = run_tests(["tests.test_bgm_service"])

        self.assertFalse(result["summary"]["ok"])
        self.assertEqual(result["returncode"], 1)


if __name__ == "__main__":
    unittest.main()
