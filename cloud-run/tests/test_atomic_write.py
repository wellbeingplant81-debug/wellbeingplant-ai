import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.utils import atomic_write


class TestAtomicReplace(unittest.TestCase):

    def test_replaces_on_first_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = os.path.join(tmp_dir, "src.txt")
            dst = os.path.join(tmp_dir, "dst.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("hello")

            atomic_write.atomic_replace(src, dst)

            self.assertTrue(os.path.exists(dst))
            self.assertFalse(os.path.exists(src))

    def test_retries_on_permission_error_then_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = os.path.join(tmp_dir, "src.txt")
            dst = os.path.join(tmp_dir, "dst.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("hello")

            real_replace = os.replace
            call_count = {"n": 0}

            def flaky_replace(s, d):
                call_count["n"] += 1
                if call_count["n"] < 3:
                    raise PermissionError("WinError 5")
                real_replace(s, d)

            with patch("os.replace", side_effect=flaky_replace), \
                 patch("time.sleep", return_value=None) as mock_sleep:
                atomic_write.atomic_replace(src, dst, retries=5, initial_delay=0.01)

            self.assertEqual(call_count["n"], 3)
            self.assertTrue(os.path.exists(dst))
            # Exponential backoff: two sleeps before the third (successful) attempt.
            self.assertEqual(mock_sleep.call_count, 2)
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            self.assertEqual(delays, [0.01, 0.02])

    def test_raises_after_exhausting_retries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = os.path.join(tmp_dir, "src.txt")
            dst = os.path.join(tmp_dir, "dst.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("hello")

            with patch("os.replace", side_effect=PermissionError("WinError 5")), \
                 patch("time.sleep", return_value=None) as mock_sleep:
                with self.assertRaises(PermissionError):
                    atomic_write.atomic_replace(src, dst, retries=3, initial_delay=0.01)

            self.assertEqual(mock_sleep.call_count, 2)


class TestAtomicWriteJson(unittest.TestCase):

    def test_writes_and_reads_back(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "nested", "data.json")
            data = {"key": "value", "n": 1}

            atomic_write.atomic_write_json(path, data)

            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), data)

    def test_uses_atomic_replace_and_survives_permission_error_retry(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "data.json")

            real_replace = os.replace
            call_count = {"n": 0}

            def flaky_replace(s, d):
                call_count["n"] += 1
                if call_count["n"] < 2:
                    raise PermissionError("WinError 5")
                real_replace(s, d)

            with patch("os.replace", side_effect=flaky_replace), \
                 patch("time.sleep", return_value=None):
                atomic_write.atomic_write_json(path, {"a": 1})

            self.assertTrue(os.path.exists(path))
            self.assertEqual(call_count["n"], 2)

    def test_cleans_up_tmp_file_on_unrecoverable_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "data.json")

            with patch("os.replace", side_effect=PermissionError("WinError 5")), \
                 patch("time.sleep", return_value=None):
                with self.assertRaises(PermissionError):
                    atomic_write.atomic_write_json(path, {"a": 1})

            remaining = os.listdir(tmp_dir)
            self.assertEqual(remaining, [])

    def test_no_api_change_signature(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "data.json")
            # Positional-args call, matching pre-existing call sites.
            atomic_write.atomic_write_json(path, {"ok": True})
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"ok": True})


if __name__ == "__main__":
    unittest.main()
