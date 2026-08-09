"""
Sprint172 - 남에게 줄 수 있는 상태인가 (Epic 58, Phase 4).

Sprint171이 세 가지를 찾았다. 여기서 그중 둘을 끝낸다.

    배경 음악    묶은 프로그램은 렌더를 끝내지 못했다
    권한         읽을 수 없는 폴더를 "자료 0개"로 받았다
    ffmpeg 두 벌  Sprint171에서 이미 고쳤다

배경 음악을 어떻게 하기로 했는가
--------------------------------
넣지 않는다. 대신 사람이 넣을 수 있는 자리를 만든다.

    <사용자 자리>\\music

저장소의 assets/music은 2.9GB에 남의 이름이 붙은 트랙들이라, 그것을
재배포하는 결정을 묶기가 대신 내릴 수 없다. 소리 하나를 지어 넣는
것도 하지 않는다 - 삐 소리를 배경 음악이라고 부르는 것은 되는 척이다.

그래서 정책을 코드가 들고 있게 한다. runtime_paths.music_root()가
어디를 보는지 한 자리에서 정하고, 켤 때 프로그램이 그 자리를 말한다.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import launcher

from app import runtime_paths
from app.services import free_workspace, local_library

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 읽을 수 없는 폴더. Windows가 계정에 상관없이 막아 두는 자리다.
BLOCKED = r"C:\Windows\System32\config"


def _unreadable() -> bool:
    if not os.path.isdir(BLOCKED):
        return False

    try:
        os.listdir(BLOCKED)
    except PermissionError:
        return True
    except OSError:
        return False

    return False


class MusicPolicyTest(unittest.TestCase):
    """1. 배경 음악을 어디서 가져오는가."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def _mp3(self, folder, name="한곡.mp3"):
        os.makedirs(folder, exist_ok=True)

        path = os.path.join(folder, name)

        with open(path, "wb") as f:
            f.write(b"ID3")

        return path

    def test_music_policy_is_explicit(self):
        """
        어디를 보는지 코드가 말한다. 순서까지.

        Sprint171에서는 이 규칙이 아무 데도 적혀 있지 않았다 -
        assets/music이라는 자리만 있었고, 묶으면 그 자리가 켤 때마다
        새로 풀리는 임시 폴더가 된다는 것을 아무도 보지 않았다.
        """

        # 1. 사람이 직접 가리킨 것이 가장 먼저다.
        mine = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, mine, ignore_errors=True)

        with patch.dict(os.environ, {runtime_paths.BGM_ENV: mine}):
            self.assertEqual(runtime_paths.music_root(), mine)

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}):
            os.environ.pop(runtime_paths.BGM_ENV, None)

            beside = os.path.join(self.home, runtime_paths.MUSIC_DIRNAME)
            packed = os.path.join(runtime_paths.bundle_root(), "assets",
                                  "music")

            # 4. 아무 데도 없으면 사람이 넣을 자리를 가리킨다.
            #    프로그램 안이 아니다 - 거기에는 넣을 수 없다.
            with patch.object(runtime_paths, "_has_music",
                              return_value=False):
                self.assertEqual(runtime_paths.music_root(), beside)

            # 3. 함께 묶여 온 것이 있으면 그것.
            with patch.object(runtime_paths, "_has_music",
                              lambda path: path == packed):
                self.assertEqual(runtime_paths.music_root(), packed)

            # 2. 사람이 제 자리에 넣어 둔 것이 묶여 온 것보다 먼저다.
            self._mp3(beside)

            with patch.object(runtime_paths, "_has_music",
                              return_value=True):
                self.assertEqual(runtime_paths.music_root(), beside)

    def test_development_still_reads_the_repository_library(self):
        """
        개발 중에는 한 글자도 달라지지 않는다.

        여기서 자리가 바뀌면 어제까지 만들던 영상의 배경 음악이
        통째로 사라진 것처럼 보인다.
        """

        environment = dict(os.environ)
        environment.pop(runtime_paths.HOME_ENV, None)
        environment.pop(runtime_paths.BGM_ENV, None)

        with patch.dict(os.environ, environment, clear=True), \
                patch.object(runtime_paths, "is_frozen", return_value=False):

            self.assertEqual(
                runtime_paths.music_root(),
                os.path.join(REPO, "assets", "music"))

    def test_the_engine_reads_that_one_place(self):
        """
        고르는 쪽이 그 자리를 쓴다.

        두 자리가 따로 정해지면, 넣어 둔 곳과 찾는 곳이 달라진다 -
        Sprint169의 ffmpeg가 정확히 그렇게 어긋났다.
        """

        from app.tools.music_review import DEFAULT_MUSIC_ROOT

        self.assertEqual(DEFAULT_MUSIC_ROOT, runtime_paths.music_root())

    def test_a_category_folder_also_counts(self):
        """분류해 둔 것도 고를 수 있다 - 고르는 쪽이 그것부터 본다."""

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        self._mp3(os.path.join(root, "calm"))

        self.assertTrue(runtime_paths._has_music(root))

    def test_the_window_says_where_to_put_music_when_there_is_none(self):
        """
        없으면 어디에 넣으라고 말한다.

        Sprint171에서는 "묶는 사람이 넣어야 합니다"라고만 했다. 받은
        사람이 할 수 있는 일이 없는 안내였다.
        """

        said = []

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch.object(runtime_paths, "_has_music",
                             return_value=False), \
                patch("builtins.print", lambda *a, **k: said.append(
                    " ".join(str(x) for x in a))):

            missing = launcher._report_music()

        self.assertEqual(missing,
                         os.path.join(self.home, runtime_paths.MUSIC_DIRNAME))

        shown = "\n".join(said)

        self.assertIn(runtime_paths.MUSIC_DIRNAME, shown)
        self.assertIn(self.home, shown)

    def test_it_says_nothing_when_music_is_there(self):
        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch.object(runtime_paths, "_has_music", return_value=True):

            self.assertIsNone(launcher._report_music())

    def test_the_first_run_makes_that_folder(self):
        """넣으라고 한 자리는 켤 때 만들어 둔다."""

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch("uvicorn.run"):

            launcher.main(["--no-browser"])

        self.assertTrue(os.path.isdir(os.path.join(
            self.home, runtime_paths.MUSIC_DIRNAME,
            runtime_paths.MUSIC_INBOX)))

    def test_the_place_we_point_at_is_the_place_that_picks(self):
        """
        넣으라고 한 자리에서 고르는 쪽이 실제로 고를 수 있다.

        한 번 어긋났다 - "mp3가 어딘가 있으면 있다"고 셌더니, 사람이
        music 바로 아래에 떨어뜨린 것을 "있다"고 말하고 렌더는 마지막에
        못 찾았다. 고르는 쪽은 inbox와 카테고리 폴더만 본다.
        """

        from app.services import bgm_service

        self.assertEqual(bgm_service.INBOX_DIR_NAME,
                         runtime_paths.MUSIC_INBOX)

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        # 바로 아래에 둔 것은 "있다"가 아니다 - 고를 수 없다.
        self._mp3(root)

        self.assertFalse(runtime_paths._has_music(root))

        with self.assertRaises(FileNotFoundError):
            bgm_service.select_bgm(music_root=root)

        # inbox에 두면 둘 다 찾는다.
        self._mp3(os.path.join(root, runtime_paths.MUSIC_INBOX))

        self.assertTrue(runtime_paths._has_music(root))
        self.assertTrue(bgm_service.select_bgm(music_root=root))


class PermissionTest(unittest.TestCase):
    """3. 읽지 못한 것을 읽었다고 하지 않는다."""

    def setUp(self):
        self.store = os.path.join(tempfile.mkdtemp(), "기억.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(self.store),
                        ignore_errors=True)

    def test_permission_error_is_visible(self):
        """
        읽을 수 없는 폴더를 고르면 그렇다고 말한다.

        Sprint171 실측: C:\\Windows\\System32\\config 를 골랐더니
        "자료 0개"로 받았다. 고른 사람은 제 파일 이름이 잘못됐다고
        생각하고 이름을 고치기 시작한다 - 실제로는 그 폴더를 열지도
        못했다.

        없는 폴더를 거절하는 규칙이 이미 있었고 그 까닭도 같았다.
        읽을 수 없는 폴더가 그 규칙에서 빠져 있었을 뿐이다.
        """

        if not _unreadable():
            self.skipTest("이 계정은 그 폴더를 읽을 수 있다")

        with self.assertRaises(free_workspace.WorkspaceError) as refused:
            free_workspace.remember(self.store, BLOCKED)

        message = str(refused.exception)

        self.assertIn("읽을 수", message)
        self.assertIn(BLOCKED, message)

        # 고르지 못했으므로 적히지도 않았다.
        self.assertIsNone(
            free_workspace.remembered(self.store)["root"])

    def test_a_readable_folder_is_still_accepted(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        free_workspace.remember(self.store, root)

        self.assertEqual(free_workspace.remembered(self.store)["root"], root)

    def test_the_scan_records_what_it_could_not_read(self):
        """
        훑다가 못 읽은 폴더가 있으면 적어 둔다.

        고른 폴더는 열리는데 그 아래 하나가 안 열리는 경우가 있다.
        그때 통째로 거절하면 나머지를 못 쓰고, 아무 말도 안 하면
        그 폴더의 파일들이 조용히 사라진다.
        """

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        os.makedirs(os.path.join(root, "images"))

        found = local_library.scan(root)

        self.assertEqual(found["unreadable"], [])

        blocked_folder = os.path.join(root, "images")

        def walking(top, *args, **kwargs):
            """os.walk가 오류를 조용히 넘기는 그 자리를 붙잡는다."""

            onerror = kwargs.get("onerror")

            failure = PermissionError(13, "액세스가 거부되었습니다")
            failure.filename = top

            if onerror is not None:
                onerror(failure)

            return iter(())

        with patch.object(local_library.os, "walk", walking):
            blocked = local_library.scan(root)

        self.assertEqual(blocked["unreadable"], [blocked_folder],
                         "못 읽은 것을 적지 않았다 - 조용한 빈 목록이다")
        self.assertEqual(blocked["items"], [])

    def test_the_index_keeps_the_old_shape(self):
        """
        적는 것이 하나 늘 뿐, 읽던 쪽은 그대로다.

        예전에 적어 둔 목록에는 그 열쇠가 없다 - 없다고 죽으면
        어제까지 만든 프로젝트가 안 열린다.
        """

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        found = local_library.scan(root)

        for key in ("version", "root", "items", "unreadable"):
            with self.subTest(key=key):
                self.assertIn(key, found)

        old = {"version": 1, "root": root, "items": []}

        self.assertEqual(local_library.counts(old),
                         {kind: 0 for kind in local_library.KINDS})


class ReleaseLayoutTest(unittest.TestCase):
    """4. 남에게 주는 폴더의 마지막 모양."""

    def test_final_release_layout(self):
        """
        무엇이 들어가고 무엇이 안 들어가는가.

        여기서 묶지 않는다 - 모양을 정하는 자리가 한 곳인지만 본다.
        실제로 만든 것은 test_deployment가 켜서 확인한다.
        """

        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import release

        from app import app_info
        from app.services import media_tools

        self.assertEqual(release.FOLDER, app_info.NAME)
        self.assertEqual(
            [name for name, _ in release.SHAPE],
            [app_info.NAME + ".exe", media_tools.BESIDE_DIRNAME, "assets",
             "README.txt"])

        # 남의 것이 함께 나가지 않는다.
        for name, source in release.SHAPE:
            with self.subTest(name=name):
                for forbidden in ("output", ".workflow", ".dataset",
                                  "credentials", ".env"):
                    self.assertNotIn(forbidden, str(source or ""))

        readme = release.readme()

        # 배경 음악을 어디에 넣는지 README가 말한다 - 넣지 않고
        # 보내기로 했으므로, 그 사실이 적혀 있지 않으면 받은 사람은
        # 렌더가 왜 안 되는지 알 수 없다.
        self.assertIn(runtime_paths.MUSIC_DIRNAME, readme)
        self.assertIn("배경 음악", readme)

    def test_the_spec_ships_no_music_by_itself(self):
        """
        묶기가 스스로 음악을 넣지 않는다.

        무엇을 재배포할지는 주는 사람이 정한다 - PACKAGING_BGM으로
        가리켰을 때만 들어간다.
        """

        spec = os.path.join(REPO, "packaging", "AI영상제작소.spec")

        with open(spec, encoding="utf-8") as f:
            body = f.read()

        self.assertIn("PACKAGING_BGM", body)

        # 저장소의 음악 폴더를 곧바로 가리키지 않는다.
        self.assertNotIn('"assets", "music"', body)


if __name__ == "__main__":
    unittest.main()
