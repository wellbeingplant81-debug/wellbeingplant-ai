"""
Sprint201 - 받은 사람의 자리에 있어야 할 것이 있는가 (Epic 59, Phase 19).

지금까지는 기록을 읽었다. 이번은 디스크를 본다.

만들지 않는다
-------------
이 스프린트에서 가장 쉽게 어길 수 있는 것이다. "없으면 만들어 주면
친절하지 않은가"는 검증이 아니라 설치다. 확인하러 갔다가 자리를 만들어
버리면, 그 다음부터는 무엇이 원래 있던 것인지 알 수 없다.

소스에 makedirs와 쓰기가 없는지 보고, 두 번 불러도 디스크가 그대로인지
본다.

packaging을 import하지 않는다
-----------------------------
release.py는 배포 폴더 밖에 남는다 - 묶인 프로그램 안에 없다. 그것을
import하면 정작 받은 사람의 자리에서 터진다. 그래서 이름은 서비스가
제 안에 두고, 여기서 release.SHAPE와 맞는지 대조한다.
"""

import ast
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import app_info, runtime_paths
from app.routers import studio as studio_router
from app.services import beta_package_validation, media_tools

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEVER_SAID = ("통과", "배포 가능", "문제 없음", "설치 완료", "안전함")


def _mark(found, key):
    for group in found["groups"]:
        for row in group["checks"]:
            if row["key"] == key:
                return row

    raise AssertionError(f"줄이 없습니다: {key}")


class Base(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.folder = tempfile.mkdtemp()

        patched = patch.dict(os.environ,
                             {runtime_paths.HOME_ENV: self.home})
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def whole_package(self):
        """받는 사람이 푸는 그 모양."""

        open(os.path.join(self.folder, app_info.NAME + ".exe"),
             "w").close()
        open(os.path.join(self.folder, "README.txt"), "w",
             encoding="utf-8").write(f"{app_info.NAME} {app_info.VERSION}\n")

        for name in (media_tools.BESIDE_DIRNAME, "assets"):
            os.makedirs(os.path.join(self.folder, name), exist_ok=True)

        for tool in ("ffmpeg.exe", "ffprobe.exe"):
            open(os.path.join(self.folder, media_tools.BESIDE_DIRNAME,
                              tool), "w").close()

    def now(self):
        return beta_package_validation.build(self.folder)


class PackageTest(Base):
    """A. 받은 폴더."""

    def test_a_whole_package_is_all_there(self):
        self.whole_package()

        found = self.now()

        for key in ("executable", "tools", "assets", "readme"):
            with self.subTest(key=key):
                self.assertIs(_mark(found, key)["ok"], True)

    def test_a_missing_exe_is_seen(self):
        self.whole_package()
        os.remove(os.path.join(self.folder, app_info.NAME + ".exe"))

        found = self.now()

        self.assertIs(_mark(found, "executable")["ok"], False)
        self.assertIs(_mark(found, "tools")["ok"], True)

    def test_a_missing_tools_folder_is_seen(self):
        self.whole_package()
        shutil.rmtree(os.path.join(self.folder, media_tools.BESIDE_DIRNAME))

        found = self.now()

        self.assertIs(_mark(found, "tools")["ok"], False)
        self.assertIs(_mark(found, "executable")["ok"], True)

    def test_a_missing_readme_is_seen(self):
        self.whole_package()
        os.remove(os.path.join(self.folder, "README.txt"))

        found = self.now()

        self.assertIs(_mark(found, "readme")["ok"], False)

    def test_the_names_match_the_packaging_shape(self):
        """
        짓는 쪽과 보는 쪽이 다른 이름을 쓰면, 잘 지어 놓고도 없다고
        한다.
        """

        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import release

        theirs = {name for name, _ in release.SHAPE}
        ours = set(beta_package_validation.SHAPE.values())

        self.assertEqual(ours, theirs)


class FirstRunTest(Base):
    """B. 처음 켜면 생기는 자리."""

    def test_a_place_that_is_not_made_yet_says_so(self):
        """
        아직 안 켠 자리에서 없는 것은 고장이 아니다. X로 찍으면
        고장 난 것으로 읽힌다.

        내 자료 자리(home) 자체는 여기서 이미 있으므로, 그 안에
        생기는 자리를 본다.
        """

        self.whole_package()

        found = self.now()

        for key in ("output", "feedback", "music_inbox"):
            with self.subTest(key=key):
                row = _mark(found, key)

                self.assertIsNone(row["ok"])
                self.assertIn("아직", row["detail"])

    def test_the_places_turn_up_once_they_exist(self):
        self.whole_package()

        runtime_paths.ensure(runtime_paths.feedback_root())

        self.assertIs(_mark(self.now(), "feedback")["ok"], True)

    def test_looking_does_not_make_them(self):
        """확인하러 갔다가 자리를 만들면 그것은 설치다."""

        self.whole_package()

        before = sorted(os.listdir(self.home))

        self.now()
        self.now()

        self.assertEqual(sorted(os.listdir(self.home)), before)


class MakesNothingTest(Base):
    """C. 만들지 않는다."""

    def test_the_program_folder_is_untouched(self):
        self.whole_package()

        before = sorted(os.listdir(self.folder))

        self.now()
        self.now()

        self.assertEqual(sorted(os.listdir(self.folder)), before)

    def test_the_source_never_writes(self):
        """
        읽는 것까지 막지는 않는다 - 안내문의 판번호를 보려면 읽어야
        한다. 막는 것은 만들고 고치고 지우는 것, 그리고 쓰기로 여는
        것이다.
        """

        source = os.path.join(REPO, "app", "services",
                              "beta_package_validation.py")

        with open(source, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        makers = ("makedirs", "mkdir", "ensure", "remove", "rmtree",
                  "rename", "replace", "unlink", "write_text", "touch",
                  "copy", "copytree")

        wrote = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None)

            if name in makers:
                wrote.append(name)

            if name in ("open", "fdopen"):
                mode = None

                if len(node.args) > 1:
                    mode = node.args[1]

                for kw in node.keywords:
                    if kw.arg == "mode":
                        mode = kw.value

                if (isinstance(mode, ast.Constant)
                        and isinstance(mode.value, str)
                        and set(mode.value) & set("wax+")):
                    wrote.append(f"{name}({mode.value})")

        self.assertEqual(wrote, [])


class PrivacyTest(Base):
    """D. 밖으로 나가도 되는가."""

    def test_nothing_personal(self):
        self.whole_package()

        folder = runtime_paths.ensure(runtime_paths.feedback_root())

        with open(os.path.join(folder, "무릎 안 됨.txt"), "w",
                  encoding="utf-8") as f:
            f.write(r"C:\Users\홍길동\내자료 를 골랐습니다")

        body = json.dumps(self.now(), ensure_ascii=False)

        for leak in (self.home, self.folder, os.path.expanduser("~"),
                     os.environ.get("USERNAME") or "USERNAME",
                     "무릎", "안 됨", "내자료", "홍길동"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, body)

        import re

        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", body))

    def test_it_never_says_it_passed(self):
        self.whole_package()

        body = json.dumps(self.now(), ensure_ascii=False)

        for said in NEVER_SAID:
            with self.subTest(said=said):
                self.assertNotIn(said, body)

    def test_it_says_it_did_not_open_the_program(self):
        """
        이 표가 "켜진다"는 뜻으로 읽히면 안 된다.
        """

        self.whole_package()

        self.assertIn("켜", self.now()["note"])


class RunAgainTest(Base):
    """E. 두 번째."""

    def test_the_answer_is_the_same(self):
        self.whole_package()

        first = self.now()
        second = self.now()

        del first["taken_at"], second["taken_at"]

        self.assertEqual(first, second)


class ToolsTest(Base):
    """F. 도구."""

    def test_tools_beside_the_program_do_not_lean_on_path(self):
        self.whole_package()

        beside = os.path.join(self.folder, media_tools.BESIDE_DIRNAME,
                              "ffmpeg.exe")

        with patch.object(media_tools, "missing", return_value=[]), \
                patch.object(media_tools, "resolve", return_value=beside):

            self.assertIs(_mark(self.now(), "beside")["ok"], True)

    def test_a_tool_from_path_is_seen(self):
        self.whole_package()

        with patch.object(media_tools, "missing", return_value=[]), \
                patch.object(media_tools, "resolve",
                             return_value="ffmpeg.exe"):

            self.assertIsNot(_mark(self.now(), "beside")["ok"], True)

    def test_a_missing_tool_says_which_one(self):
        self.whole_package()

        with patch.object(media_tools, "missing", return_value=["ffmpeg"]):
            row = _mark(self.now(), "ffmpeg")

            self.assertIs(row["ok"], False)


class TwoPlacesAgreeTest(Base):
    """G. 데이터 분리를 두 자리가 같게 본다."""

    def test_the_separation_matches_readiness(self):
        from app.services import beta_readiness

        self.whole_package()

        ours = _mark(self.now(), "separated")["ok"]
        theirs = {row["key"]: row["ok"]
                  for row in beta_readiness.build()["checks"]}

        self.assertEqual(ours, theirs["data_separated"])


class ApiTest(Base):
    """H. 서버와 화면."""

    def setUp(self):
        super().setUp()

        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)

    def test_the_api_answers(self):
        answer = self.client.get("/studio/api/beta-package-validation")

        self.assertEqual(answer.status_code, 200)

        found = answer.json()

        for key in ("taken_at", "version", "groups", "note", "report"):
            with self.subTest(key=key):
                self.assertIn(key, found)

    def test_the_screen_has_the_button(self):
        page = studio_router.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/beta-package-validation", page)
        self.assertIn("패키지 확인", page)


if __name__ == "__main__":
    unittest.main()
