import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.bgm_service import select_bgm


def _make_music_root(tmp_dir, categories_and_files=None, inbox_files=None):
    music_root = os.path.join(tmp_dir, "music")
    inbox_dir = os.path.join(music_root, "inbox")
    os.makedirs(inbox_dir)

    for name in (inbox_files or []):
        with open(os.path.join(inbox_dir, name), "wb") as f:
            f.write(b"fake mp3 bytes")

    for category, files in (categories_and_files or {}).items():
        category_dir = os.path.join(music_root, category)
        os.makedirs(category_dir)
        for name in files:
            with open(os.path.join(category_dir, name), "wb") as f:
                f.write(b"fake mp3 bytes")

    return music_root


class TestSelectFromClassifiedCategory(unittest.TestCase):

    def test_uses_category_when_it_has_tracks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(
                tmp_dir,
                categories_and_files={"calm": ["a.mp3", "b.mp3"]},
                inbox_files=["should_not_be_picked.mp3"],
            )

            path = select_bgm("calm", music_root=music_root)

            self.assertTrue(path.startswith(os.path.join(music_root, "calm")))
            self.assertTrue(os.path.isfile(path))

    def test_selection_uses_injected_random_fn(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(
                tmp_dir, categories_and_files={"calm": ["a.mp3", "b.mp3", "c.mp3"]}
            )

            path = select_bgm(
                "calm", music_root=music_root, random_fn=lambda choices: sorted(choices)[0]
            )

            self.assertEqual(os.path.basename(path), "a.mp3")

    def test_ignores_non_mp3_files_in_category(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, categories_and_files={"calm": ["a.mp3"]})
            with open(os.path.join(music_root, "calm", "notes.txt"), "w") as f:
                f.write("not audio")

            path = select_bgm("calm", music_root=music_root)

            self.assertEqual(os.path.basename(path), "a.mp3")


class TestFallsBackToInboxWhenCategoryEmpty(unittest.TestCase):

    def test_empty_category_falls_back_to_inbox(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(
                tmp_dir,
                categories_and_files={"calm": []},
                inbox_files=["x.mp3", "y.mp3"],
            )

            path = select_bgm("calm", music_root=music_root)

            self.assertTrue(path.startswith(os.path.join(music_root, "inbox")))

    def test_no_category_given_falls_back_to_inbox(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, inbox_files=["x.mp3"])

            path = select_bgm(music_root=music_root)

            self.assertTrue(path.startswith(os.path.join(music_root, "inbox")))

    def test_switches_back_to_category_once_classified(self):
        # Music Review Tool이 나중에 분류를 마치면, 코드 변경 없이도
        # 자동으로 카테고리 폴더를 우선 사용해야 한다.
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(
                tmp_dir,
                categories_and_files={"calm": []},
                inbox_files=["x.mp3"],
            )

            before = select_bgm("calm", music_root=music_root)
            self.assertTrue(before.startswith(os.path.join(music_root, "inbox")))

            # Review Tool이 한 곡을 calm/으로 분류했다고 가정
            with open(os.path.join(music_root, "calm", "classified.mp3"), "wb") as f:
                f.write(b"fake mp3 bytes")

            after = select_bgm("calm", music_root=music_root)
            self.assertTrue(after.startswith(os.path.join(music_root, "calm")))


class TestInvalidCategoryRaises(unittest.TestCase):

    def test_nonexistent_category_folder_raises_clear_exception(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, inbox_files=["x.mp3"])

            with self.assertRaises(ValueError) as ctx:
                select_bgm("not_a_real_category", music_root=music_root)

            self.assertIn("not_a_real_category", str(ctx.exception))


class TestNoTracksAnywhereRaises(unittest.TestCase):

    def test_empty_category_and_empty_inbox_raises_clear_exception(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir, categories_and_files={"calm": []})

            with self.assertRaises(FileNotFoundError):
                select_bgm("calm", music_root=music_root)

    def test_no_category_and_empty_inbox_raises_clear_exception(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = _make_music_root(tmp_dir)

            with self.assertRaises(FileNotFoundError):
                select_bgm(music_root=music_root)


if __name__ == "__main__":
    unittest.main()
