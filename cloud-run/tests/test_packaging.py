"""
Sprint169 - Python 없이도 켤 수 있게 (Epic 58, Phase 1).

지금까지 이 프로그램을 켜려면 Python과 가상환경과 uvicorn 명령이
필요했다. 만드는 사람에게는 당연하지만, 쓰는 사람에게는 아니다.

여기서 지키는 것은 "묶어도 돌아가는가"이다
------------------------------------------
묶은 exe를 이 테스트가 만들지는 않는다 - 몇 분이 걸리고, 만든 것을
검사하는 일과 만드는 일은 다르다. 대신 묶였을 때 깨질 자리들을 본다.

    사용자 것이 프로그램 안에 있는가   있으면 끌 때 같이 사라진다
    static이 목록에 들어 있는가        빠지면 화면이 안 뜬다
    ffmpeg를 찾을 수 있는가            없으면 영상이 안 만들어진다
    서버가 뜨는가                      진입점이 실제로 도는가

개발 중에는 한 글자도 달라지지 않는다
-------------------------------------
자리를 옮기면 어제까지 만든 프로젝트가 사라진 것처럼 보인다. 그래서
묶였을 때와 AI_STUDIO_HOME을 준 때만 옮긴다.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import launcher

from app import runtime_paths
from app.services import media_tools, project_service

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ServerStartsTest(unittest.TestCase):
    """1. 실행 파일이 서버를 띄운다."""

    def test_executable_starts_server(self):
        """
        진입점이 실제로 uvicorn을 부르고, 그 주소로 화면이 열린다.

        진짜로 띄우지는 않는다 - 포트를 잡고 창을 여는 일은 이
        테스트가 할 일이 아니다. 부르는 모양이 맞는지를 본다.
        """

        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}), \
                patch.object(launcher, "webbrowser") as browser, \
                patch("uvicorn.run") as run:

            self.assertEqual(launcher.main(["--no-browser"]), 0)

            self.assertTrue(run.called)

            from app.main import app as served

            self.assertIs(run.call_args.args[0], served)
            self.assertEqual(run.call_args.kwargs["host"], launcher.HOST)

            port = run.call_args.kwargs["port"]

            self.assertGreater(port, 0)

            # --no-browser면 열지 않는다.
            browser.open.assert_not_called()

    def test_it_picks_a_free_port(self):
        """
        포트를 고정하지 않는다.

        이미 쓰이고 있으면 켜지지 않고, 그때 나는 오류는 사람이 읽을
        수 있는 말이 아니다.
        """

        import socket

        port = launcher._free_port()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # 방금 비어 있다고 한 자리에 실제로 앉을 수 있다.
            sock.bind((launcher.HOST, port))

    def test_it_makes_the_user_folders(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        target = os.path.join(home, "새 자리")

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: target}), \
                patch("uvicorn.run"):

            launcher.main(["--no-browser"])

        for name in ("output", ".workflow", ".dataset"):
            with self.subTest(name=name):
                self.assertTrue(os.path.isdir(os.path.join(target, name)))

    def test_it_opens_the_studio_page(self):
        """빈 화면이 아니라 쓰는 화면을 연다."""

        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        opened = []

        # Sprint219 - _open_browser 가 포트를 함께 받는다(서버가 실제로
        # 받을 때까지 기다리려면 무엇을 두드릴지 알아야 한다). 대역도
        # 그 모양이어야 한다 - 확인하는 것은 예전 그대로 "쓰는 화면을
        # 연다"이다.
        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}), \
                patch("uvicorn.run"), \
                patch.object(launcher, "_open_browser",
                             lambda url, **kw: opened.append(url)):

            launcher.main([])

        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].endswith("/studio"))

    def test_it_waits_for_the_server_before_opening(self):
        """
        Sprint219 - 브라우저에게 넘기는 주소가 실제로 받는 자리여야
        한다. 포트를 함께 넘기지 않으면 기다릴 방법이 없다.
        """

        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        given = {}

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}), \
                patch("uvicorn.run"), \
                patch.object(launcher, "_open_browser",
                             lambda url, **kw: given.update(
                                 url=url, **kw)):

            launcher.main([])

        self.assertIn("ready_port", given)
        self.assertIn(f":{given['ready_port']}/", given["url"])


class StaticFilesTest(unittest.TestCase):
    """2. 화면 파일이 묶는 목록에 있다."""

    def test_static_files_exist_in_bundle(self):
        """
        빠지면 화면이 통째로 안 뜬다.

        묶는 목록(spec)이 static 폴더를 들고 가는지, 그리고 그 안에
        실제로 화면이 있는지 둘 다 본다.
        """

        static = os.path.join(REPO, "app", "static")

        for name in ("studio.html", "queue.html", "replay.html"):
            with self.subTest(name=name):
                self.assertTrue(os.path.exists(os.path.join(static, name)))

        spec = os.path.join(REPO, "packaging", "AI영상제작소.spec")

        self.assertTrue(os.path.exists(spec), "묶는 목록이 없다")

        with open(spec, encoding="utf-8") as f:
            body = f.read()

        self.assertIn("app/static", body.replace("\\\\", "/"))

    def test_the_router_finds_the_page_by_its_own_path(self):
        """
        화면 경로를 __file__에서 짓는다.

        묶이면 그 자리가 _MEIPASS 아래가 되고, 그때도 같은 규칙으로
        찾아야 한다.
        """

        from app.routers import studio

        self.assertTrue(os.path.exists(studio._PAGE))
        self.assertTrue(studio._PAGE.endswith("studio.html"))


class FfmpegTest(unittest.TestCase):
    """3. ffmpeg를 찾을 수 있다."""

    def test_ffmpeg_is_available(self):
        found = media_tools.available()

        self.assertIsNotNone(found[media_tools.FFMPEG])
        self.assertIsNotNone(found[media_tools.FFPROBE])
        self.assertEqual(media_tools.missing(), [])

    def test_the_bundled_one_is_used_when_there_is_no_path(self):
        """
        PATH에 없어도 ffmpeg는 찾는다.

        moviepy가 쓰는 imageio-ffmpeg가 제 것을 들고 오기 때문이다 -
        이미 있는 의존성이라 따로 받아 넣지 않아도 된다.
        """

        with patch.object(shutil, "which", return_value=None):
            found = media_tools.resolve(media_tools.FFMPEG)

        self.assertTrue(os.path.exists(found))
        self.assertIn("ffmpeg", os.path.basename(found).lower())

    def test_a_given_path_wins(self):
        """사람이 가리킨 것이 먼저다."""

        fake = os.path.join(tempfile.mkdtemp(), "ffmpeg.exe")
        self.addCleanup(shutil.rmtree, os.path.dirname(fake),
                        ignore_errors=True)

        open(fake, "wb").close()

        with patch.dict(os.environ,
                        {media_tools.ENV[media_tools.FFMPEG]: fake}):
            self.assertEqual(media_tools.resolve(media_tools.FFMPEG), fake)

    def test_the_bundle_puts_them_where_we_look_for_them(self):
        """
        함께 보낸 것을 실제로 찾을 수 있는가.

        test_ffmpeg_is_available은 이것을 못 잡는다 - 개발 PC의 PATH에
        둘 다 있으니 어디에 넣든 초록불이다. 실제로 처음 만든 exe는
        ffmpeg\\ffprobe.exe\\ffprobe.exe에 넣어 놓고 못 찾았고, 그
        결과가 "음성 길이 None"이었다.

        그래서 넣는 자리와 찾는 자리를 마주 붙여 본다.

        Sprint170 - 자리가 번들 안에서 exe 옆의 tools/로 옮겨졌다.
        보는 것은 그대로다: 넣은 자리와 찾는 자리가 같은가.
        """

        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import bundled_tools

        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        placed = bundled_tools.place(root)

        self.assertTrue(placed, "함께 보낼 것이 하나도 없다")

        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)

        with patch.object(runtime_paths, "program_dir", return_value=root), \
                patch.object(runtime_paths, "bundle_root",
                             return_value=empty), \
                patch.object(media_tools, "_from_imageio",
                             return_value=None), \
                patch.object(shutil, "which", return_value=None), \
                patch.dict(os.environ, {}, clear=False):

            for name in (media_tools.FFMPEG, media_tools.FFPROBE):
                os.environ.pop(media_tools.ENV[name], None)

            for name, _ in bundled_tools.sources():
                with self.subTest(name=name):
                    found = media_tools.resolve(name)

                    self.assertTrue(
                        os.path.isfile(found),
                        f"{name}을 넣어 놓고도 못 찾는다: {found}")
                    self.assertEqual(
                        os.path.relpath(found, root),
                        bundled_tools.landing(name))

    def test_the_spec_does_not_invent_its_own_places(self):
        """
        묶는 목록이 제 나름의 자리를 다시 짓지 않는다.

        spec은 테스트가 부를 수 없는 파일이라, 그 안에 규칙을 두면
        아무도 보지 않는 규칙이 된다.
        """

        spec = os.path.join(REPO, "packaging", "AI영상제작소.spec")

        with open(spec, encoding="utf-8") as f:
            body = f.read()

        # 설명글과 주석은 빼고 본다.
        #
        # 이 저장소는 같은 함정에 여러 번 걸렸다 - 무엇을 하지 말라는
        # 규칙을 소스 텍스트로 검사하면, 그 규칙을 설명하는 제 주석에
        # 걸린다. Sprint171에서 실제로 그랬다: 자리가 어긋났던 일을
        # 적어 둔 주석 안의 "tools/ffmpeg.exe"가 위반으로 잡혔다.
        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        for invented in ("ffmpeg/ffprobe.exe", "ffmpeg/ffmpeg.exe",
                         "ffmpeg\\\\ffprobe.exe", "tools/ffmpeg.exe"):
            with self.subTest(invented=invented):
                self.assertNotIn(invented, code)

    def test_it_says_what_is_missing_instead_of_pretending(self):
        with patch.object(media_tools, "resolve", return_value="없는것"), \
                patch.object(shutil, "which", return_value=None):

            self.assertEqual(sorted(media_tools.missing()),
                             ["ffmpeg", "ffprobe"])


class UserDataOutsideBundleTest(unittest.TestCase):
    """4. 사용자 것이 프로그램 안에 있지 않다."""

    def test_user_data_not_inside_bundle(self):
        """
        묶였을 때 사용자 것은 %APPDATA% 아래로 간다.

        프로그램 안에 두면 끌 때 같이 사라지고, Program Files에
        설치했다면 아예 쓸 수도 없다.
        """

        appdata = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, appdata, ignore_errors=True)

        environment = {"APPDATA": appdata}

        with patch.dict(os.environ, environment, clear=False), \
                patch.object(runtime_paths, "is_frozen", return_value=True):

            os.environ.pop(runtime_paths.HOME_ENV, None)

            home = runtime_paths.home()

            self.assertTrue(home.startswith(appdata))
            self.assertIn(runtime_paths.APP_DIRNAME, home)

            for path in (runtime_paths.output_root(),
                         runtime_paths.workflow_root(),
                         runtime_paths.dataset_root()):
                with self.subTest(path=path):
                    self.assertTrue(path.startswith(appdata))

    def test_development_stays_exactly_where_it_was(self):
        """
        개발 중에는 한 글자도 달라지지 않는다.

        자리를 옮기면 어제까지 만든 프로젝트가 사라진 것처럼 보인다.
        """

        environment = dict(os.environ)
        environment.pop(runtime_paths.HOME_ENV, None)

        with patch.dict(os.environ, environment, clear=True), \
                patch.object(runtime_paths, "is_frozen", return_value=False):

            self.assertEqual(runtime_paths.output_root(), "output")
            self.assertEqual(
                runtime_paths.dataset_root(),
                os.path.join(REPO, ".dataset"))
            self.assertEqual(
                runtime_paths.workflow_root(),
                os.path.join(REPO, ".workflow"))

    def test_the_spec_ships_no_user_data(self):
        """
        묶는 목록에 사용자 것이 없다.

        넣으면 남의 프로젝트와 API 키가 함께 배포된다.
        """

        spec = os.path.join(REPO, "packaging", "AI영상제작소.spec")

        with open(spec, encoding="utf-8") as f:
            body = f.read().replace("\\\\", "/")

        for name in ("output", ".workflow", ".dataset", "credentials",
                     ".env"):
            with self.subTest(name=name):
                self.assertNotIn(f"'{name}'", body)

    def test_a_given_home_is_honoured(self):
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: target}):
            self.assertEqual(runtime_paths.home(), target)
            self.assertEqual(runtime_paths.output_root(),
                             os.path.join(target, "output"))


class FreeModeFromPackageTest(unittest.TestCase):
    """5. 묶인 자리에서도 무료 모드가 돈다."""

    def test_free_mode_runs_from_package(self):
        """
        사용자 자리를 다른 곳으로 옮겨 두고 무료 모드를 돌린다.

        묶인 프로그램이 겪는 것과 같은 상황이다 - 코드와 데이터가
        서로 다른 자리에 있다.
        """

        from fastapi.testclient import TestClient
        from PIL import Image

        from app.main import app
        from app.routers import studio as studio_router
        from app.services import (
            asset_integration_service, local_library, scene_tts_service,
        )

        home = tempfile.mkdtemp()
        workspace = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)

        for name in ("무릎 스트레칭", "허리 세우기"):
            path = os.path.join(workspace, "images", f"{name}.png")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Image.new("RGB", (64, 64)).save(path)

        for number in (1, 2):
            path = os.path.join(workspace, "voices", f"scene{number}.wav")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            subprocess.run(
                [media_tools.resolve(media_tools.FFMPEG), "-y", "-f", "lavfi",
                 "-i", "sine=f=440:d=0.4", path],
                capture_output=True, check=True)

        project = os.path.join(home, "output", "20260808_120000")
        os.makedirs(project, exist_ok=True)

        scenes = [
            {"scene": 1, "narration": "무릎을 펴 주세요",
             "image_prompt": "무릎 스트레칭"},
            {"scene": 2, "narration": "허리를 세웁니다",
             "image_prompt": "허리 세우기"},
        ]

        import json

        with open(os.path.join(project, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "t", "scenes": scenes}, f, ensure_ascii=False)

        store = os.path.join(home, ".workflow", "free_workspace.json")

        real_project = studio_router._project_path
        real_store = studio_router._workspace_store

        studio_router._project_path = lambda project_id: project
        studio_router._workspace_store = lambda: store

        try:
            with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
                client = TestClient(app)

                chosen = client.put("/studio/api/workspace",
                                    json={"root": workspace})

                self.assertEqual(chosen.status_code, 200)
                self.assertEqual(chosen.json()["counts"]["images"], 2)

                client.post("/studio/api/review/p1/library", json={})

                prepared = client.get(
                    "/studio/api/review/p1/preparation").json()

                self.assertEqual(prepared["state"], "ready")

                # 실제로 만들어지는가.
                local_library.load(project)

                for scene in scenes:
                    target = os.path.join(
                        project, "images", f"scene{scene['scene']}.png")

                    asset_integration_service._select_ai_first(
                        scene["image_prompt"], target, "wellbeing", False,
                        scene=scene, provider="local_stock")

                    self.assertTrue(os.path.exists(target))

                scene_tts_service.create_scene_tts(
                    scenes, project, provider="local_voice")

                from app.services import scene_order

                self.assertEqual(
                    scene_order.render_problems(project, scenes), [])
        finally:
            studio_router._project_path = real_project
            studio_router._workspace_store = real_store

        # 프로그램 자리에는 아무것도 안 생겼다.
        self.assertFalse(os.path.exists(
            os.path.join(REPO, "output", "20260808_120000")))


if __name__ == "__main__":
    unittest.main()
