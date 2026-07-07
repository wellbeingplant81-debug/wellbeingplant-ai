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

from app.tools import music_review


def _make_music_root(tmp_dir, inbox_files=None):
    music_root = os.path.join(tmp_dir, "music")
    inbox_dir = os.path.join(music_root, "inbox")
    os.makedirs(inbox_dir)
    os.makedirs(os.path.join(music_root, "metadata"))

    for name in (inbox_files or []):
        with open(os.path.join(inbox_dir, name), "wb") as f:
            f.write(b"fake mp3 bytes")

    return music_root


class TestScanInbox(unittest.TestCase):

    def test_finds_mp3_files_only_and_sorted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(
                tmp_dir, ["b.mp3", "a.mp3", "note.txt", "c.MP3"],
            )
            inbox_dir = os.path.join(music_root, "inbox")

            result = music_review.scan_inbox(inbox_dir)

            self.assertEqual(result, ["a.mp3", "b.mp3", "c.MP3"])

    def test_missing_inbox_directory_returns_empty_list(self):
        result = music_review.scan_inbox("/no/such/inbox/dir")
        self.assertEqual(result, [])

    def test_ignores_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["a.mp3"])
            inbox_dir = os.path.join(music_root, "inbox")
            os.makedirs(os.path.join(inbox_dir, "subfolder.mp3"))

            result = music_review.scan_inbox(inbox_dir)

            self.assertEqual(result, ["a.mp3"])


class TestResolveKeyCategoryMapping(unittest.TestCase):

    def test_number_keys_map_to_expected_categories(self):
        expected = {
            "1": "bright", "2": "calm", "3": "dramatic", "4": "energetic",
            "5": "emotional", "6": "food", "7": "healing", "8": "mystery",
            "9": "nature", "10": "technology", "11": "tension",
            "12": "uplifting", "0": "rejected",
        }
        for key, category in expected.items():
            self.assertEqual(music_review.resolve_key(key), category)

    def test_skip_key_case_insensitive(self):
        self.assertEqual(music_review.resolve_key("s"), music_review.ACTION_SKIP)
        self.assertEqual(music_review.resolve_key("S"), music_review.ACTION_SKIP)

    def test_quit_key_case_insensitive(self):
        self.assertEqual(music_review.resolve_key("q"), music_review.ACTION_QUIT)
        self.assertEqual(music_review.resolve_key("Q"), music_review.ACTION_QUIT)

    def test_whitespace_is_trimmed(self):
        self.assertEqual(music_review.resolve_key("  1  "), "bright")
        self.assertEqual(music_review.resolve_key(" q "), music_review.ACTION_QUIT)


class TestResolveKeyInvalid(unittest.TestCase):

    def test_out_of_range_number_is_invalid(self):
        self.assertIsNone(music_review.resolve_key("13"))
        self.assertIsNone(music_review.resolve_key("99"))

    def test_non_numeric_garbage_is_invalid(self):
        self.assertIsNone(music_review.resolve_key("abc"))

    def test_empty_and_none_are_invalid(self):
        self.assertIsNone(music_review.resolve_key(""))
        self.assertIsNone(music_review.resolve_key("   "))
        self.assertIsNone(music_review.resolve_key(None))


class TestMoveFile(unittest.TestCase):

    def test_moves_file_to_destination_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["Dream.mp3"])
            src = os.path.join(music_root, "inbox", "Dream.mp3")
            dest_dir = os.path.join(music_root, "healing")

            dest_path = music_review.move_file(src, dest_dir)

            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(dest_path))
            self.assertEqual(dest_path, os.path.join(dest_dir, "Dream.mp3"))

    def test_creates_destination_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["a.mp3"])
            src = os.path.join(music_root, "inbox", "a.mp3")
            dest_dir = os.path.join(music_root, "bright")

            music_review.move_file(src, dest_dir)

            self.assertTrue(os.path.isdir(dest_dir))


class TestMoveFileDuplicateHandling(unittest.TestCase):

    def test_existing_file_with_same_name_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["Dream.mp3"])
            src = os.path.join(music_root, "inbox", "Dream.mp3")
            dest_dir = os.path.join(music_root, "healing")
            os.makedirs(dest_dir)

            existing = os.path.join(dest_dir, "Dream.mp3")
            with open(existing, "wb") as f:
                f.write(b"original healing track")

            dest_path = music_review.move_file(src, dest_dir)

            self.assertEqual(dest_path, os.path.join(dest_dir, "Dream_1.mp3"))
            self.assertTrue(os.path.exists(existing))
            with open(existing, "rb") as f:
                self.assertEqual(f.read(), b"original healing track")

    def test_multiple_collisions_increment_suffix(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["Dream.mp3"])
            src = os.path.join(music_root, "inbox", "Dream.mp3")
            dest_dir = os.path.join(music_root, "healing")
            os.makedirs(dest_dir)

            for name in ("Dream.mp3", "Dream_1.mp3"):
                with open(os.path.join(dest_dir, name), "wb") as f:
                    f.write(b"x")

            dest_path = music_review.move_file(src, dest_dir)

            self.assertEqual(dest_path, os.path.join(dest_dir, "Dream_2.mp3"))


class TestMetadataUpdate(unittest.TestCase):

    def test_record_classification_writes_new_entry(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = os.path.join(tmp_dir, "music_library.json")

            entry = music_review.record_classification(
                metadata_path, "Dream.mp3", "healing", classified_at="2026-01-01T00:00:00+00:00",
            )

            self.assertEqual(entry, {
                "file": "Dream.mp3",
                "category": "healing",
                "classified_at": "2026-01-01T00:00:00+00:00",
                "reviewed": True,
            })

            with open(metadata_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(saved["version"], 1)
            self.assertEqual(saved["tracks"], [entry])

    def test_record_classification_initializes_missing_library_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = os.path.join(tmp_dir, "music_library.json")
            self.assertFalse(os.path.exists(metadata_path))

            music_review.record_classification(metadata_path, "a.mp3", "bright")

            self.assertTrue(os.path.exists(metadata_path))

    def test_preserves_other_existing_tracks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = os.path.join(tmp_dir, "music_library.json")
            music_review.record_classification(metadata_path, "a.mp3", "bright")

            music_review.record_classification(metadata_path, "b.mp3", "calm")

            with open(metadata_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(len(saved["tracks"]), 2)
            self.assertEqual({t["file"] for t in saved["tracks"]}, {"a.mp3", "b.mp3"})


class TestMetadataDuplicateHandling(unittest.TestCase):

    def test_reclassifying_same_file_updates_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = os.path.join(tmp_dir, "music_library.json")

            music_review.record_classification(metadata_path, "Dream.mp3", "healing")
            music_review.record_classification(metadata_path, "Dream.mp3", "calm")

            with open(metadata_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(len(saved["tracks"]), 1)
            self.assertEqual(saved["tracks"][0]["category"], "calm")


class TestClassifyOne(unittest.TestCase):

    def test_moves_file_and_updates_metadata_together(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["Dream.mp3"])
            inbox_dir = os.path.join(music_root, "inbox")

            result = music_review.classify_one(inbox_dir, "Dream.mp3", "healing", music_root)

            expected_dest = os.path.join(music_root, "healing", "Dream.mp3")
            self.assertEqual(result["dest_path"], expected_dest)
            self.assertTrue(os.path.exists(expected_dest))
            self.assertFalse(os.path.exists(os.path.join(inbox_dir, "Dream.mp3")))
            self.assertEqual(result["entry"]["category"], "healing")

            metadata_path = os.path.join(music_root, "metadata", "music_library.json")
            with open(metadata_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["tracks"][0]["file"], "Dream.mp3")


class TestRunReviewSessionSkip(unittest.TestCase):

    def test_skip_leaves_file_in_inbox_and_no_metadata_entry(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["a.mp3"])

            music_review.run_review_session(
                music_root=music_root,
                input_fn=lambda prompt: "S",
                play_fn=lambda path: None,
            )

            self.assertTrue(os.path.exists(os.path.join(music_root, "inbox", "a.mp3")))
            metadata_path = os.path.join(music_root, "metadata", "music_library.json")
            self.assertFalse(os.path.exists(metadata_path))


class TestRunReviewSessionQuit(unittest.TestCase):

    def test_quit_stops_before_processing_remaining_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["a.mp3", "b.mp3"])

            music_review.run_review_session(
                music_root=music_root,
                input_fn=lambda prompt: "Q",
                play_fn=lambda path: None,
            )

            self.assertTrue(os.path.exists(os.path.join(music_root, "inbox", "a.mp3")))
            self.assertTrue(os.path.exists(os.path.join(music_root, "inbox", "b.mp3")))

    def test_quit_after_first_file_does_not_touch_second(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["a.mp3", "b.mp3"])
            responses = iter(["1", "Q"])

            music_review.run_review_session(
                music_root=music_root,
                input_fn=lambda prompt: next(responses),
                play_fn=lambda path: None,
            )

            self.assertFalse(os.path.exists(os.path.join(music_root, "inbox", "a.mp3")))
            self.assertTrue(os.path.exists(os.path.join(music_root, "bright", "a.mp3")))
            self.assertTrue(os.path.exists(os.path.join(music_root, "inbox", "b.mp3")))


class TestRunReviewSessionInvalidKey(unittest.TestCase):

    def test_invalid_key_reprompts_until_valid(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["a.mp3"])
            responses = iter(["99", "xyz", "1"])

            music_review.run_review_session(
                music_root=music_root,
                input_fn=lambda prompt: next(responses),
                play_fn=lambda path: None,
            )

            self.assertTrue(os.path.exists(os.path.join(music_root, "bright", "a.mp3")))


class TestRunReviewSessionFullFlow(unittest.TestCase):

    def test_classifies_multiple_files_in_order_and_calls_play_fn(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, ["a.mp3", "b.mp3"])
            responses = iter(["1", "2"])
            played = []

            music_review.run_review_session(
                music_root=music_root,
                input_fn=lambda prompt: next(responses),
                play_fn=lambda path: played.append(path),
            )

            self.assertTrue(os.path.exists(os.path.join(music_root, "bright", "a.mp3")))
            self.assertTrue(os.path.exists(os.path.join(music_root, "calm", "b.mp3")))
            self.assertEqual(len(played), 2)

            metadata_path = os.path.join(music_root, "metadata", "music_library.json")
            with open(metadata_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(len(saved["tracks"]), 2)

    def test_no_inbox_files_completes_without_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, [])

            music_review.run_review_session(
                music_root=music_root,
                input_fn=lambda prompt: "Q",
                play_fn=lambda path: None,
            )


class TestPlayMusic(unittest.TestCase):

    def test_play_music_calls_os_startfile(self):
        with patch("os.startfile", create=True) as mock_startfile:
            music_review.play_music("some/path.mp3")
            mock_startfile.assert_called_once_with("some/path.mp3")

    def test_play_music_does_not_raise_when_startfile_fails(self):
        with patch("os.startfile", create=True, side_effect=OSError("boom")):
            music_review.play_music("some/path.mp3")


if __name__ == "__main__":
    unittest.main()
