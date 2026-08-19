"""
Sprint170 - 받은 사람이 그냥 켤 수 있는가 (Epic 58, Phase 2).

Sprint169는 exe를 만들었다. 만들어지는 것과 남에게 줄 수 있는 것은
다르다 - 다음 넷이 아직 없었다.

    첫 실행     자리는 만들지만 설정은 없다
    포트        비어 있는 자리를 고르지만, 사람이 고른 자리가 차
                있을 때 무슨 일이 나는지 정해 두지 않았다
    오류        죽으면 traceback이 창에 쏟아진다. 사람이 읽을 수
                있는 말이 아니고, 창이 닫히면 그것마저 사라진다
    판번호      어느 판을 쓰고 있는지 아무 데도 없다

여기서 지키는 것
----------------
    첫 실행이 자리와 설정을 만든다
    두 번째 실행이 그것을 덮지 않는다      ← 갱신해도 살아남는다
    쓰이고 있는 포트를 피한다
    끄면 끝난다
    exe가 제 판번호를 들고 있다
    죽을 때 남길 것을 남긴다
"""

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import launcher

from app import app_info, error_log, runtime_paths, settings

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FirstRunTest(unittest.TestCase):
    """1. 첫 실행."""

    def setUp(self):
        self.home = os.path.join(tempfile.mkdtemp(), "처음")
        self.addCleanup(shutil.rmtree, os.path.dirname(self.home),
                        ignore_errors=True)

    def test_first_run_creates_user_directory(self):
        """
        아무것도 없는 자리에서 켜면 사용자 자리가 생긴다.

        받은 사람의 PC에는 이 폴더가 없다. 없으면 첫 저장에서 죽는다.
        """

        self.assertFalse(os.path.exists(self.home))

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch("uvicorn.run"):

            launcher.main(["--no-browser"])

        for name in ("output", ".workflow", ".dataset"):
            with self.subTest(name=name):
                self.assertTrue(os.path.isdir(os.path.join(self.home, name)))

        self.assertTrue(os.path.isfile(os.path.join(self.home,
                                                    settings.FILENAME)))

    def test_the_first_settings_are_the_declared_defaults(self):
        """기본 설정은 한 자리에서만 정한다."""

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}):
            made = settings.ensure()

            for key, value in settings.DEFAULTS.items():
                with self.subTest(key=key):
                    self.assertEqual(made[key], value)

            # 어느 판이 만들었는지 적어 둔다 - 갱신을 알아보려면 필요하다.
            self.assertEqual(made[settings.CREATED_BY], app_info.VERSION)

    def test_existing_user_data_survives_update(self):
        """
        갱신해도 사람이 쌓아 둔 것과 바꿔 둔 설정이 살아남는다.

        새 판을 덮어씌우는 것이 곧 갱신이다. 그때 설정을 기본값으로
        되돌리면, 쓰던 사람은 제가 바꾼 것이 사라진 것을 보게 된다.
        """

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch("uvicorn.run"):

            launcher.main(["--no-browser"])

            # 쓰던 사람이 바꾼 것과 만들어 둔 것.
            settings.save({settings.OPEN_BROWSER: False, "내가 넣은 것": 7})

            project = os.path.join(self.home, "output", "20260808_090000")
            os.makedirs(project)

            with open(os.path.join(project, "script.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"title": "내 것"}, f, ensure_ascii=False)

            # 새 판이 다시 켜진다.
            launcher.main(["--no-browser"])

            kept = settings.load()

            self.assertIs(kept[settings.OPEN_BROWSER], False)
            self.assertEqual(kept["내가 넣은 것"], 7)

            with open(os.path.join(project, "script.json"),
                      encoding="utf-8") as f:
                self.assertEqual(json.load(f)["title"], "내 것")

    def test_a_new_setting_is_filled_in_without_touching_the_old_ones(self):
        """
        판이 올라가면서 설정이 늘 수 있다.

        없는 것만 채운다 - 있는 것을 건드리면 위의 약속이 깨진다.
        """

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}):
            settings.ensure()
            settings.save({settings.OPEN_BROWSER: False})

            with patch.dict(settings.DEFAULTS, {"새로 생긴 것": "기본"},
                            clear=False):
                filled = settings.ensure()

            self.assertIs(filled[settings.OPEN_BROWSER], False)
            self.assertEqual(filled["새로 생긴 것"], "기본")

    def test_a_broken_settings_file_does_not_stop_the_program(self):
        """
        설정이 깨져 있어도 켜진다.

        읽지 못하는 파일 하나 때문에 프로그램 전체가 안 켜지면, 사람은
        고칠 방법을 알 수 없다.
        """

        runtime_paths.ensure(self.home)

        with open(os.path.join(self.home, settings.FILENAME), "w",
                  encoding="utf-8") as f:
            f.write("{ 이건 설정이 아니다")

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}):
            self.assertEqual(settings.load()[settings.OPEN_BROWSER],
                             settings.DEFAULTS[settings.OPEN_BROWSER])

    def test_settings_that_cannot_be_written_do_not_stop_the_program(self):
        """
        설정을 적지 못해도 켜진다.

        설정은 켜는 데 필요한 것이 아니라 편하자고 있는 것이다. 그것
        하나 때문에 프로그램이 안 켜지면, 사람은 화면을 보지도 못한
        채로 무엇이 잘못됐는지 알아내야 한다.

        적지 못했다는 것을 감추지도 않는다 - 다음에 켤 때 바꾼 것이
        없어져 있으면 그것대로 놀란다.
        """

        runtime_paths.ensure(self.home)

        # 설정이 놓일 자리를 폴더가 차지하고 있다.
        os.makedirs(os.path.join(self.home, settings.FILENAME))

        said = []

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch("uvicorn.run"), \
                patch("builtins.print", lambda *a, **k: said.append(
                    " ".join(str(x) for x in a))):

            self.assertEqual(launcher.main(["--no-browser"]), 0)

        self.assertTrue(any("설정" in line for line in said),
                        f"적지 못한 것을 말하지 않았다: {said}")

    def test_a_failed_save_is_not_swallowed(self):
        """
        사람이 바꾼 것을 적지 못하면 그대로 알린다.

        첫 실행이 기본값을 못 적는 것과, 사람이 고른 것을 못 적는 것은
        다르다. 뒤엣것을 조용히 넘기면 화면은 "저장했습니다"라고 하고
        다음에 켤 때 없다.
        """

        runtime_paths.ensure(self.home)
        os.makedirs(os.path.join(self.home, settings.FILENAME))

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}):
            with self.assertRaises(Exception):
                settings.save({settings.OPEN_BROWSER: False})


class RunStabilityTest(unittest.TestCase):
    """2. 실행 안정화."""

    def test_port_conflict_is_handled(self):
        """
        사람이 고른 자리가 차 있으면 비어 있는 자리로 간다.

        멈추지 않는다 - 그때 나는 오류는 사람이 읽을 수 있는 말이
        아니고, 무엇을 어떻게 하라는 것인지도 알 수 없다.
        """

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
            taken.bind((launcher.HOST, 0))
            taken.listen(1)

            busy = taken.getsockname()[1]

            self.assertFalse(launcher._is_free(busy))

            chosen = launcher.choose_port(busy)

            self.assertNotEqual(chosen, busy)
            self.assertTrue(launcher._is_free(chosen))

    def test_a_free_asked_port_is_used_as_asked(self):
        """비어 있으면 사람이 고른 그 자리를 쓴다."""

        wanted = launcher._free_port()

        self.assertEqual(launcher.choose_port(wanted), wanted)

    def test_the_asked_port_comes_from_the_command_line(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        wanted = launcher._free_port()

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}), \
                patch("uvicorn.run") as run:

            launcher.main(["--no-browser", "--port", str(wanted)])

            self.assertEqual(run.call_args.kwargs["port"], wanted)

    def test_process_shutdown(self):
        """
        끄면 끝난다.

        서버가 멈춘 뒤에도 남는 스레드가 있으면 창은 닫혔는데 프로그램은
        살아 있고, 다음에 켤 때 포트가 물려 있다. 브라우저를 여는 일은
        daemon이라 붙잡지 않는다.
        """

        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        before = {t.name for t in threading.enumerate()}

        def interrupted(*_, **__):
            raise KeyboardInterrupt

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}), \
                patch("uvicorn.run", interrupted), \
                patch.object(launcher, "webbrowser"):

            # 브라우저를 여는 스레드까지 띄운 채로 끊는다.
            self.assertEqual(launcher.main([]), 0)

        lingering = [
            t for t in threading.enumerate()
            if t.name not in before and not t.daemon
        ]

        self.assertEqual(lingering, [], "끈 뒤에도 붙잡는 것이 남았다")

    def test_browser_failure_does_not_take_the_server_down(self):
        """
        브라우저를 못 열어도 서버는 돈다.

        열지 못했다는 말은 한다 - 아무 일도 안 일어나면 사람은 프로그램이
        멈춘 줄 안다. 주소는 이미 창에 찍혀 있다.
        """

        said = []

        with patch.object(launcher.webbrowser, "open",
                          side_effect=OSError("못 연다")), \
                patch.object(launcher, "OPEN_AFTER_SECONDS", 0), \
                patch("builtins.print", lambda *a, **k: said.append(
                    " ".join(str(x) for x in a))):

            thread = launcher._open_browser("http://127.0.0.1:1/studio")
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertTrue(any("주소" in line for line in said),
                        f"직접 열라는 말이 없다: {said}")


class ErrorReportTest(unittest.TestCase):
    """3. 오류 처리."""

    def test_error_log_written(self):
        """
        죽을 때 남길 것을 남긴다.

        창이 닫히면 화면의 글자는 사라진다. 파일로 남겨야 사람이
        보내 줄 수 있다.
        """

        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
            try:
                raise ValueError("무엇인가 잘못됐다")
            except ValueError as failed:
                written = error_log.write(failed)

        self.assertTrue(os.path.isfile(written))
        self.assertTrue(written.startswith(os.path.join(home,
                                                        error_log.DIRNAME)))

        with open(written, encoding="utf-8") as f:
            body = f.read()

        for mark in ("ValueError", "무엇인가 잘못됐다", "Traceback",
                     app_info.VERSION):
            with self.subTest(mark=mark):
                self.assertIn(mark, body)

    def test_the_traceback_is_not_thrown_at_the_user(self):
        """
        창에는 사람이 읽을 수 있는 말과 로그 자리만 남긴다.

        traceback은 파일에 있다. 창에 쏟으면 읽히지도 않고, 그 밑에
        무엇을 하라는 말이 있어도 안 보인다.
        """

        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        said = []

        def blows_up(*_, **__):
            raise RuntimeError("엔진이 안 켜진다")

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}), \
                patch("uvicorn.run", blows_up), \
                patch("builtins.print", lambda *a, **k: said.append(
                    " ".join(str(x) for x in a))):

            code = launcher.main(["--no-browser"])

        self.assertNotEqual(code, 0, "죽었는데 잘 끝난 척한다")

        shown = "\n".join(said)

        self.assertNotIn("Traceback", shown)
        self.assertNotIn("blows_up", shown)
        self.assertIn(error_log.DIRNAME, shown)

        # Sprint219 - 같은 폴더에 켜는 자취(startup.log)도 함께 쌓인다.
        # 세는 것은 여전히 "이번에 죽어서 남은 오류 기록"이고 그것은
        # 하나여야 한다 - 자취까지 세면 무엇을 지키는 시험인지가
        # 흐려진다.
        logs = [name
                for name in os.listdir(os.path.join(home, error_log.DIRNAME))
                if name.startswith("error-")]

        self.assertEqual(len(logs), 1)

        with open(os.path.join(home, error_log.DIRNAME, logs[0]),
                  encoding="utf-8") as f:
            self.assertIn("엔진이 안 켜진다", f.read())


class AppInfoTest(unittest.TestCase):
    """4. 앱 정보."""

    def test_bundle_has_version_info(self):
        """
        exe가 제 판번호를 들고 있다.

        Windows가 파일 속성에서 보여 주는 그것이다 - 받은 사람이
        "어느 판을 쓰고 있는가"를 물을 때 볼 수 있는 유일한 자리다.

        묶는 일은 여기서 하지 않는다(몇 분이 걸린다). 대신 묶을 때
        넣을 것을 만들어 보고, 이미 만들어 둔 exe가 있으면 그 안을
        실제로 읽는다.
        """

        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import version_resource

        text = version_resource.text()

        self.assertIn(app_info.NAME, text)
        self.assertIn(app_info.VERSION, text)
        self.assertEqual(version_resource.numbers(),
                         tuple(int(p) for p in app_info.VERSION.split("."))
                         + (0,))

        built = os.path.join(REPO, "dist", app_info.NAME,
                             app_info.NAME + ".exe")

        if not os.path.exists(built):
            self.skipTest("아직 묶은 것이 없다 - 만든 뒤에 실측한다")

        found = version_resource.read_from(built)

        self.assertEqual(found["ProductName"], app_info.NAME)
        self.assertEqual(found["FileVersion"], app_info.VERSION)

    def test_it_knows_its_own_name_and_version(self):
        self.assertEqual(app_info.NAME, runtime_paths.APP_DIRNAME)

        parts = app_info.VERSION.split(".")

        self.assertEqual(len(parts), 3)
        self.assertTrue(all(p.isdigit() for p in parts))

    def test_the_build_date_is_measured_not_guessed(self):
        """
        빌드 날짜는 묶을 때 적힌다.

        개발 중에는 묶은 적이 없으므로 없다고 말한다 - 오늘 날짜를
        적으면 "언제 묶은 것인가"라는 물음에 거짓으로 답하게 된다.
        """

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        with patch.object(runtime_paths, "bundle_root", return_value=root):
            self.assertIsNone(app_info.build_date())

            with open(os.path.join(root, app_info.BUILD_FILENAME), "w",
                      encoding="utf-8") as f:
                json.dump({"built_at": "2026-08-08T12:00:00"}, f)

            self.assertEqual(app_info.build_date(), "2026-08-08T12:00:00")

    def test_the_window_says_which_version_it_is(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        said = []

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}), \
                patch("uvicorn.run"), \
                patch("builtins.print", lambda *a, **k: said.append(
                    " ".join(str(x) for x in a))):

            launcher.main(["--no-browser"])

        shown = "\n".join(said)

        self.assertIn(app_info.NAME, shown)
        self.assertIn(app_info.VERSION, shown)


class ReleaseLayoutTest(unittest.TestCase):
    """5. 배포 구조."""

    def setUp(self):
        sys.path.insert(0, os.path.join(REPO, "packaging"))

    def test_the_release_folder_has_the_declared_shape(self):
        """
        받는 사람이 푸는 폴더의 모양.

            AI영상제작소/
              AI영상제작소.exe
              tools/
              assets/
              README.txt
        """

        import release

        self.assertEqual(release.FOLDER, app_info.NAME)
        self.assertEqual(
            [name for name, _ in release.SHAPE],
            [app_info.NAME + ".exe", "tools", "assets", "README.txt"])

    def test_the_tools_beside_the_exe_are_found(self):
        """
        tools/에 둔 것을 프로그램이 찾는다.

        묶인 프로그램에서 bundle_root()는 풀린 임시 폴더다. exe가
        실제로 놓인 자리는 그것이 아니므로, 옆의 tools/를 보려면
        program_dir()이 있어야 한다 - 없으면 넣어 두고도 못 찾는다.
        """

        import release

        from app.services import media_tools

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        tools = os.path.join(root, release.TOOLS_DIRNAME)
        os.makedirs(tools)

        for name in (media_tools.FFMPEG, media_tools.FFPROBE):
            open(os.path.join(tools, name + ".exe"), "wb").close()

        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)

        with patch.object(runtime_paths, "program_dir", return_value=root), \
                patch.object(runtime_paths, "bundle_root", return_value=empty), \
                patch.object(shutil, "which", return_value=None), \
                patch.object(media_tools, "_from_imageio",
                             return_value=None):

            for name in (media_tools.FFMPEG, media_tools.FFPROBE):
                with self.subTest(name=name):
                    self.assertEqual(
                        media_tools.resolve(name),
                        os.path.join(tools, name + ".exe"))

    def test_the_program_dir_is_where_the_exe_sits(self):
        """
        묶였을 때 프로그램 자리는 exe가 놓인 폴더다.

        _MEIPASS가 아니다 - 그것은 켤 때마다 새로 생기는 임시 폴더라
        사람이 거기에 무엇을 둘 수 없다.
        """

        with patch.object(runtime_paths, "is_frozen", return_value=True), \
                patch.object(sys, "executable", r"C:\받은것\프로그램.exe"):

            self.assertEqual(runtime_paths.program_dir(), r"C:\받은것")

    def test_the_readme_says_where_the_user_data_lives(self):
        import release

        text = release.readme()

        self.assertIn(app_info.NAME, text)
        self.assertIn(app_info.VERSION, text)
        self.assertIn(runtime_paths.APP_DIRNAME, text)
        self.assertIn(release.TOOLS_DIRNAME, text)

    def test_the_release_ships_no_user_data(self):
        """푼 폴더에 남의 프로젝트나 키가 없다."""

        import release

        for name, source in release.SHAPE:
            with self.subTest(name=name):
                for forbidden in ("output", ".workflow", ".dataset",
                                  "credentials", ".env"):
                    self.assertNotIn(forbidden, str(source or ""))


if __name__ == "__main__":
    unittest.main()
