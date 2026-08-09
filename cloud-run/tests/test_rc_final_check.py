"""
Sprint173 - 남에게 주기 직전의 마지막 점검 (Epic 58, Phase 5).

이름이 test_rc_final_check인 까닭
-------------------------------
test_final_check는 Sprint162가 이미 쓰고 있다 - 그쪽은 "렌더 버튼을
누르기 전에 막는 것이 있는가"이고, 여기는 "남에게 줄 묶음이 맞는가"다.
같은 이름을 쓰려다 그 파일을 통째로 덮어썼다(Sprint173에서 실제로
그랬고, 회귀 수가 16 줄어 드러났다).

앞의 네 스프린트가 만든 것을 여기서 한 번에 본다. 새로 짓지 않는다 -
어긋난 곳이 없는지만 본다.

무엇이 어긋날 수 있는가
-----------------------
    판번호      네 자리에 따로 적히면 어느 날 서로 다른 말을 한다
    안내        프로그램이 하는 말과 README가 하는 말이 다르면,
                받은 사람은 둘 중 무엇이 맞는지 알 수 없다
    폴더        묶은 것에 있어야 할 것이 빠지거나, 없어야 할 것이 든다

이 저장소는 앞의 두 가지로 이미 여러 번 걸렸다 - ffmpeg를 넣는 자리와
찾는 자리가 달랐고(Sprint169), 음악을 넣으라고 한 자리와 고르는 자리가
달랐다(Sprint172). 같은 종류의 어긋남을 여기서 미리 막는다.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import launcher

from app import app_info, error_log, runtime_paths
from app.services import media_tools

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RELEASE = os.path.join(REPO, "dist", app_info.NAME)
EXE = os.path.join(RELEASE, app_info.NAME + ".exe")


class VersionTest(unittest.TestCase):
    """4. 판번호가 네 자리에서 같은 말을 한다."""

    def test_release_version_consistency(self):
        """
        exe 속성 · README · 화면 · 창이 모두 같은 판을 말한다.

        받은 사람이 "어느 판입니까"라는 물음에 답할 때 어디를 보든
        같은 답이 나와야 한다. 네 자리에 손으로 적어 두면 어느 날
        하나만 고쳐진다.
        """

        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import release

        # 1. README
        readme = release.readme()

        self.assertIn(app_info.VERSION, readme)

        # 2. 창(켤 때 찍는 것)
        self.assertIn(app_info.VERSION, app_info.title())
        self.assertIn(app_info.NAME, app_info.title())

        # 3. 화면(Studio 페이지)
        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        self.assertIn(app_info.VERSION, page,
                      "화면이 판번호를 말하지 않는다")
        self.assertIn(app_info.NAME, page)

        # 4. exe 속성. 묶은 것이 있을 때만 - 여기서 묶지 않는다.
        if not os.path.isfile(EXE):
            self.skipTest("아직 묶은 것이 없다")

        import version_resource

        found = version_resource.read_from(EXE)

        self.assertEqual(found["ProductName"], app_info.NAME)
        self.assertEqual(found["FileVersion"], app_info.VERSION)
        self.assertEqual(found["ProductVersion"], app_info.VERSION)

    def test_nobody_writes_the_version_by_hand(self):
        """
        판번호는 app_info 하나에서만 온다.

        화면·README·묶기 어느 쪽도 제 손으로 적지 않는다 - 적는
        순간 그 자리가 다음 판에 뒤처진다.
        """

        watched = (
            os.path.join(REPO, "app", "static", "studio.html"),
            os.path.join(REPO, "packaging", "release.py"),
            os.path.join(REPO, "packaging", "version_resource.py"),
        )

        for path in watched:
            with self.subTest(path=os.path.basename(path)):
                with open(path, encoding="utf-8") as f:
                    body = f.read()

                # 설명글과 주석은 뺀다 - 규칙을 적어 둔 글이 그 규칙에
                # 걸리는 함정을 이 저장소는 이미 여러 번 겪었다.
                code = re.sub(r'"""[\s\S]*?"""', "", body)
                code = re.sub(r"(?m)#.*$", "", code)
                code = re.sub(r"(?s)<!--.*?-->", "", code)

                self.assertNotIn(app_info.VERSION, code,
                                 "판번호를 손으로 적었다")


class FirstRunGuidanceTest(unittest.TestCase):
    """1. 처음 켠 사람이 무엇을 해야 하는지 안다."""

    def setUp(self):
        self.home = os.path.join(tempfile.mkdtemp(), "처음")
        self.addCleanup(shutil.rmtree, os.path.dirname(self.home),
                        ignore_errors=True)

    def _boot(self):
        """아무것도 없는 자리에서 한 번 켜고, 창이 한 말을 돌려준다."""

        said = []

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch("uvicorn.run"), \
                patch("builtins.print", lambda *a, **k: said.append(
                    " ".join(str(x) for x in a))):

            code = launcher.main(["--no-browser"])

        return code, "\n".join(said)

    def test_first_run_user_guidance(self):
        """
        아무것도 없는 상태에서 켜면, 무엇이 없고 어디에 넣는지 말한다.

        받은 사람에게는 이 창이 전부다. 여기서 침묵하면 사람은 화면만
        보다가 렌더에서 처음으로 문제를 만난다 - 몇 분 뒤다.
        """

        with patch.object(runtime_paths, "_has_music", return_value=False):
            code, said = self._boot()

        self.assertEqual(code, 0)

        # 무엇을 켰는가.
        self.assertIn(app_info.NAME, said)
        self.assertIn(app_info.VERSION, said)

        # 내 것이 어디 쌓이는가.
        self.assertIn(self.home, said)

        # 무엇이 없는가. 그리고 어디에 넣는가.
        inbox = os.path.join(self.home, runtime_paths.MUSIC_DIRNAME,
                             runtime_paths.MUSIC_INBOX)

        self.assertIn("배경 음악이 없어", said)
        self.assertIn(inbox, said)

        # 어떻게 끄는가.
        self.assertIn("Ctrl+C", said)

    def test_the_guidance_points_at_folders_that_exist(self):
        """
        넣으라고 한 자리는 실제로 만들어져 있다.

        없는 폴더를 가리키면 사람은 만들어야 하는지 이름을 잘못 봤는지
        알 수 없다.
        """

        with patch.object(runtime_paths, "_has_music", return_value=False):
            _, said = self._boot()

        pointed = [
            word for word in said.replace("\n", " ").split()
            if word.startswith(self.home)
        ]

        self.assertTrue(pointed, "가리킨 자리가 없다")

        for path in pointed:
            with self.subTest(path=path):
                self.assertTrue(os.path.isdir(path),
                                f"가리켰는데 없는 자리다: {path}")

    def test_the_screen_tells_where_materials_go(self):
        """
        자료가 없을 때 화면이 무엇을 하라고 말한다.

        자료 안내는 창이 아니라 화면이 한다 - 폴더를 고르는 일이
        화면에서 일어나기 때문이다. 창에까지 옮겨 적으면 두 자리가
        따로 늙는다.
        """

        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        for mark in ("내 자료 폴더 선택", "images", "voices"):
            with self.subTest(mark=mark):
                self.assertIn(mark, page)

    def test_the_readme_and_the_program_say_the_same_thing(self):
        """
        README가 말하는 자리와 프로그램이 만드는 자리가 같다.

        다르면 받은 사람은 둘 중 무엇이 맞는지 알 수 없고, 보통
        README를 믿는다.
        """

        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import release

        readme = release.readme()

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch("uvicorn.run"):

            launcher.main(["--no-browser"])

        # README가 이름을 대는 것들이 실제로 생겨 있다.
        for name in ("output", runtime_paths.MUSIC_DIRNAME,
                     ".workflow", ".dataset"):
            with self.subTest(name=name):
                self.assertIn(name, readme)
                self.assertTrue(os.path.isdir(
                    os.path.join(self.home, name)))

        # 오류 기록 자리도 README가 말한다. 그 폴더는 죽을 때 생긴다 -
        # 미리 만들지 않는다(빈 logs 폴더는 "무슨 일이 있었나" 하게
        # 만든다).
        self.assertIn(error_log.DIRNAME, readme)
        self.assertFalse(os.path.exists(
            os.path.join(self.home, error_log.DIRNAME)))

        # 함께 온 것들의 이름도 같다.
        self.assertIn(media_tools.BESIDE_DIRNAME, readme)


class CleanInstallTest(unittest.TestCase):
    """3. 받은 사람이 하는 일을 처음부터 끝까지."""

    def setUp(self):
        if not os.path.isfile(EXE):
            self.skipTest(f"아직 묶은 것이 없다: {RELEASE}")

        self.work = tempfile.mkdtemp(prefix="설치_")
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

        self.home = os.path.join(self.work, "유저")

    def test_clean_install_journey(self):
        """
        압축을 풀고, 켜고, 안내대로 하고, 영상을 받는다.

        test_render_complete_from_release_bundle과 겹치는 듯하지만
        시작이 다르다 - 저기는 폴더를 복사해서 시작하고, 여기는 zip을
        만들어 풀고 시작한다. 압축을 한 번 돌면 빠지는 것이 있는지는
        풀어 봐야 안다.

        그리고 여기는 "안내를 보고 그대로 했더니 되더라"를 본다.
        프로그램이 하라는 대로만 하고, 우리가 아는 지름길을 쓰지 않는다.
        """

        from tests.test_deployment import Running

        # ── 압축해서 새 자리에 푼다 ─────────────────────────────
        import zipfile

        archive = os.path.join(self.work, app_info.NAME + ".zip")

        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for base, _, names in os.walk(RELEASE):
                for name in names:
                    path = os.path.join(base, name)
                    zf.write(path, os.path.join(
                        app_info.NAME, os.path.relpath(path, RELEASE)))

        with zipfile.ZipFile(archive) as zf:
            zf.extractall(os.path.join(self.work, "푼것"))

        folder = os.path.join(self.work, "푼것", app_info.NAME)

        self.assertEqual(sorted(os.listdir(folder)),
                         sorted(os.listdir(RELEASE)),
                         "압축을 돌고 나니 빠진 것이 있다")

        program = os.path.join(folder, app_info.NAME + ".exe")
        ffmpeg = os.path.join(folder, media_tools.BESIDE_DIRNAME,
                              "ffmpeg.exe")

        # ── 처음 켠다. 무엇이 없다고 하는지 듣는다 ──────────────
        first = Running(program, self.home)

        self.assertIsNotNone(first.url, f"켜지지 않았다: {first.said}")
        self.assertIsNotNone(first.page())

        told = first.rest(1.5)
        first.stop()

        self.assertIn("배경 음악이 없어", told)

        # 창이 가리킨 자리를 그대로 읽는다 - 우리가 아는 경로를 쓰지
        # 않는다. 안내가 틀렸다면 여기서 걸려야 한다.
        pointed = [
            word for word in told.replace("\n", " ").split()
            if word.startswith(self.home)
            and runtime_paths.MUSIC_DIRNAME in word
        ]

        self.assertTrue(pointed, f"어디에 넣으라는 말이 없다: {told}")

        inbox = pointed[0]

        self.assertTrue(os.path.isdir(inbox), f"없는 자리를 가리켰다: {inbox}")

        # ── 안내대로 mp3를 넣는다 ───────────────────────────────
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=f=220:d=20",
             "-filter:a", "volume=0.05", "-b:a", "96k",
             os.path.join(inbox, "검사용 소리.mp3")],
            capture_output=True, check=True)

        # ── 내 자료를 모은다 ────────────────────────────────────
        workspace = os.path.join(self.work, "내자료")

        for kind in ("images", "voices"):
            os.makedirs(os.path.join(workspace, kind))

        for name, colour in (("무릎 스트레칭", "red"),
                             ("허리 세우기", "blue")):
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi",
                 "-i", f"color=c={colour}:s=1080x1920:d=1", "-frames:v", "1",
                 os.path.join(workspace, "images", f"{name}.png")],
                capture_output=True, check=True)

        for number, seconds in ((1, 2.4), (2, 2.1)):
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi",
                 "-i", f"sine=f=330:d={seconds}", "-ar", "24000", "-ac", "1",
                 os.path.join(workspace, "voices", f"scene{number}.wav")],
                capture_output=True, check=True)

        # ── 다시 켠다. 이제는 아무 말도 없어야 한다 ─────────────
        running = Running(program, self.home)
        self.addCleanup(running.stop)

        self.assertIsNotNone(running.page())
        self.assertNotIn("배경 음악이 없어", running.rest(1.5))

        # 켠 판이 화면에 그대로 뜬다.
        self.assertIn(app_info.VERSION, running.page())

        # ── 자료 선택 ───────────────────────────────────────────
        chosen = running.call("/api/workspace", {"root": workspace}, "PUT")

        self.assertEqual(chosen["counts"]["images"], 2)
        self.assertEqual(chosen["counts"]["voice"], 2)

        # ── 무료 제작 ───────────────────────────────────────────
        import json

        from tests.test_deployment import DeploymentTest

        made = running.call(
            "/api/production/project",
            {"raw": json.dumps(DeploymentTest.SCRIPT, ensure_ascii=False),
             "topic": DeploymentTest.SCRIPT["title"],
             "channel": "wellbeing"}, "POST")

        project_id = made["project_id"]

        running.call(
            f"/api/review/{project_id}/providers",
            {"providers": {"image": "local_stock", "voice": "local_voice"}},
            "PUT")
        running.call(f"/api/review/{project_id}/library", {}, "POST")

        self.assertEqual(
            running.call(f"/api/review/{project_id}/preparation")["state"],
            "ready")

        for step in ("images", "voices"):
            running.call(f"/api/review/{project_id}/{step}", {}, "POST")

        # ── 렌더 ────────────────────────────────────────────────
        job = running.call(f"/api/review/{project_id}/render", {}, "POST")

        self.assertNotIn("__error__", job, f"렌더를 못 걸었다: {job}")

        outcome = None
        deadline = time.time() + 1200

        while time.time() < deadline:
            state = running.call(f"/api/jobs/{job['job_id']}")

            if state.get("state") in ("done", "failed"):
                outcome = state
                break

            time.sleep(5)

        self.assertIsNotNone(outcome, "렌더가 끝나지 않았다")
        self.assertEqual(outcome.get("state"), "done",
                         f"렌더가 실패했다: {outcome.get('error')}")

        # ── MP4 확인 ────────────────────────────────────────────
        check = running.call(f"/api/review/{project_id}/output-check")

        self.assertEqual(check["state"], "ready",
                         f"결과에 문제가 있다: {check.get('issues')}")
        self.assertTrue(check["video"]["exists"])

        project = os.path.join(self.home, "output", project_id)
        made_files = [
            os.path.join(base, name)
            for base, _, names in os.walk(project)
            for name in names
            if name.lower().endswith(".mp4")
        ]

        self.assertTrue(made_files, "MP4가 없다")
        self.assertGreater(max(os.path.getsize(p) for p in made_files),
                           10_000)

        # ── 프로그램 폴더는 그대로다 ────────────────────────────
        self.assertEqual(sorted(os.listdir(folder)),
                         sorted(os.listdir(RELEASE)))


class BundleIntegrityTest(unittest.TestCase):
    """2. 묶은 폴더에 있을 것만 있다."""

    def setUp(self):
        if not os.path.isfile(EXE):
            self.skipTest(f"아직 묶은 것이 없다: {RELEASE}")

    def test_final_bundle_integrity(self):
        """
        받는 사람이 푸는 폴더에 무엇이 있는가.

        빠진 것도, 남의 것도 없어야 한다. 사람 손으로 만든 폴더라
        무엇이 섞여 들어가도 눈에 잘 띄지 않는다.
        """

        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import release

        expected = {name for name, _ in release.SHAPE}

        self.assertEqual(set(os.listdir(RELEASE)), expected)

        # 도구가 실제로 있고, 이름이 찾는 쪽과 같다.
        tools = os.path.join(RELEASE, media_tools.BESIDE_DIRNAME)

        for name in (media_tools.FFMPEG, media_tools.FFPROBE):
            with self.subTest(name=name):
                path = os.path.join(tools, name + ".exe")

                self.assertTrue(os.path.isfile(path), f"{name}이 없다")
                self.assertGreater(os.path.getsize(path), 1_000_000)

        # 남의 것이 섞여 들어가지 않았다.
        forbidden = (".env", "credentials", "output", ".workflow",
                     ".dataset", ".git")

        for base, dirs, names in os.walk(RELEASE):
            for name in list(dirs) + names:
                with self.subTest(name=name):
                    self.assertNotIn(name, forbidden,
                                     f"묶은 폴더에 {name}이 들어 있다")

        # 음악은 넣지 않기로 했다 - 넣었다면 그것은 결정이 바뀐 것이고,
        # README도 함께 바뀌어야 한다.
        packed = os.path.join(RELEASE, "assets", runtime_paths.MUSIC_DIRNAME)

        self.assertFalse(os.path.isdir(packed),
                         "음악을 넣었다면 README의 안내도 바꿔야 한다")

    def test_the_exe_carries_no_secrets(self):
        """
        키가 함께 나가지 않았다.

        묶기가 저장소 전체를 훑으므로, 한 번 잘못 적으면 그대로 퍼진다.
        exe 안을 통째로 뒤지지는 않는다 - 묶는 목록이 무엇을 가리키는지
        본다.
        """

        spec = os.path.join(REPO, "packaging", app_info.NAME + ".spec")

        with open(spec, encoding="utf-8") as f:
            body = f.read()

        code = re.sub(r'"""[\s\S]*?"""', "", body)
        code = re.sub(r"(?m)#.*$", "", code)

        # 따옴표에 싸인 이름만 본다.
        #
        # 맨 문자열로 찾으면 os.environ의 ".env"가 걸린다 - 실제로
        # 걸렸다. 이 저장소가 반복해서 겪은 함정이라 여기서도 조심한다.
        for secret in (".env", "credentials", "client_secret", "token"):
            for quote in ("'", '"'):
                with self.subTest(secret=secret, quote=quote):
                    self.assertNotIn(f"{quote}{secret}{quote}", code)


if __name__ == "__main__":
    unittest.main()
