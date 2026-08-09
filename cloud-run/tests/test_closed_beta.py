"""
Sprint174 - 밖의 사람 한 명이 첫 영상을 만들 수 있는가 (Epic 58, Phase 6).

여기까지는 우리가 만든 것을 우리가 켰다. 이제 남이 켠다. 남은 우리가
아는 것을 하나도 모른다 - 어느 폴더가 무엇인지도, 무엇이 잘못됐을 때
어디를 봐야 하는지도.

그래서 셋을 더한다
------------------
    피드백 자리   겪은 일을 적어 둘 곳. 머릿속에만 있으면 사라진다
    문의처        막혔을 때 물어볼 곳
    정보 복사     "어느 판이고 무엇이 없느냐"에 답하려면 사람이 그것을
                  먼저 알아야 한다. 창을 뒤져 옮겨 적게 하지 않는다

셋 다 사람이 곤란해진 순간에 쓰인다. 그때는 이미 화가 나 있으므로,
찾아 헤매게 하면 안 쓰고 만다.
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

from app import app_info, error_log, runtime_paths
from app.services import media_tools

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ContactTest(unittest.TestCase):
    """문의처는 한 자리에서만 온다."""

    def test_the_contact_is_declared_once(self):
        """
        네 자리가 같은 곳을 가리킨다.

        판번호로 이미 겪었다 - 화면에 손으로 적어 둔 "Studio v1"이
        여러 판을 지나도록 남아 있었다. 문의처는 더 나쁘다. 바뀐 줄
        모르고 없는 주소로 보내면 그 사람은 답을 못 받는다.
        """

        self.assertTrue(app_info.CONTACT, "문의처가 비어 있다")

        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import release

        self.assertIn(app_info.CONTACT, release.readme())

        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        self.assertIn(app_info.CONTACT, page)

    def test_nobody_writes_the_contact_by_hand(self):
        watched = (
            os.path.join(REPO, "app", "static", "studio.html"),
            os.path.join(REPO, "packaging", "release.py"),
            os.path.join(REPO, "launcher.py"),
        )

        for path in watched:
            with self.subTest(path=os.path.basename(path)):
                with open(path, encoding="utf-8") as f:
                    self.assertNotIn(app_info.CONTACT, f.read(),
                                     "문의처를 손으로 적었다")


class FeedbackPlaceTest(unittest.TestCase):
    """겪은 일을 적어 둘 자리."""

    def setUp(self):
        self.home = os.path.join(tempfile.mkdtemp(), "처음")
        self.addCleanup(shutil.rmtree, os.path.dirname(self.home),
                        ignore_errors=True)

    def _boot(self):
        said = []

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch("uvicorn.run"), \
                patch("builtins.print", lambda *a, **k: said.append(
                    " ".join(str(x) for x in a))):

            launcher.main(["--no-browser"])

        return "\n".join(said)

    def test_the_first_run_makes_the_feedback_place(self):
        said = self._boot()

        where = os.path.join(self.home, runtime_paths.FEEDBACK_DIRNAME)

        self.assertTrue(os.path.isdir(where))

        # 어디에 적으라는 말이 있어야 그 폴더가 쓰인다.
        self.assertIn(where, said)

    def test_it_leaves_a_note_about_what_to_write(self):
        """
        빈 폴더는 무엇을 적으라는 말이 아니다.

        무엇을 적어야 우리가 고칠 수 있는지는 우리가 안다. 사람이
        짐작하게 두지 않는다.
        """

        self._boot()

        note = os.path.join(self.home, runtime_paths.FEEDBACK_DIRNAME,
                            launcher.FEEDBACK_NOTE)

        self.assertTrue(os.path.isfile(note))

        with open(note, encoding="utf-8") as f:
            body = f.read()

        self.assertIn(app_info.CONTACT, body)
        self.assertIn(error_log.DIRNAME, body)

    def test_it_never_overwrites_what_the_person_wrote(self):
        """
        두 번째 실행이 적어 둔 것을 덮지 않는다.

        설정에서 정한 규칙과 같다 - 없는 것만 채운다.
        """

        self._boot()

        note = os.path.join(self.home, runtime_paths.FEEDBACK_DIRNAME,
                            launcher.FEEDBACK_NOTE)

        with open(note, "w", encoding="utf-8") as f:
            f.write("내가 겪은 일을 여기 적었다")

        mine = os.path.join(self.home, runtime_paths.FEEDBACK_DIRNAME,
                            "2026-08-09 안 되던 것.txt")

        with open(mine, "w", encoding="utf-8") as f:
            f.write("이미지가 안 걸린다")

        self._boot()

        with open(note, encoding="utf-8") as f:
            self.assertEqual(f.read(), "내가 겪은 일을 여기 적었다")

        self.assertTrue(os.path.isfile(mine))


class AboutTest(unittest.TestCase):
    """무엇을 쓰고 있는지 한 번에 알려 준다."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)

    def _about(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}):
            answer = TestClient(app).get("/studio/api/about")

        self.assertEqual(answer.status_code, 200)

        return answer.json()

    def test_it_reports_what_is_actually_running(self):
        """
        "어느 판이고 무엇이 없느냐"에 사람이 답할 수 있게 한다.

        지어내지 않는다 - 전부 지금 이 프로그램이 실제로 보고 있는
        값이다.
        """

        found = self._about()

        self.assertEqual(found["name"], app_info.NAME)
        self.assertEqual(found["version"], app_info.VERSION)
        self.assertEqual(found["contact"], app_info.CONTACT)
        self.assertEqual(found["build"], app_info.build_date())
        self.assertEqual(found["home"], self.home)

        # 도구는 있는 그대로. 없으면 없다고 적힌다.
        self.assertEqual(sorted(found["tools"]),
                         sorted([media_tools.FFMPEG, media_tools.FFPROBE]))

        self.assertIn("music", found)
        self.assertIn("feedback", found)

    def test_it_says_when_music_is_missing(self):
        """
        없으면 없다고 하고, 넣을 자리를 그대로 알려 준다.

        기대값도 같은 자리 안에서 짓는다 - 밖에서 지으면 개발 PC의
        저장소 경로가 나온다(실제로 그렇게 한 번 틀렸다).
        """

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: self.home}), \
                patch.object(runtime_paths, "_has_music", return_value=False):

            expected = os.path.join(runtime_paths.music_root(),
                                    runtime_paths.MUSIC_INBOX)

            found = self._about()

        self.assertFalse(found["music"]["ready"])
        self.assertEqual(found["music"]["where"], expected)
        self.assertTrue(expected.startswith(self.home))

    def test_the_text_is_built_in_one_place(self):
        """
        붙여 넣을 글은 서버가 짓는다.

        화면이 제 나름대로 조립하면, 우리가 받아 보는 글의 모양이
        사람마다 달라진다 - 무엇이 빠졌는지 알 수 없게 된다.
        """

        found = self._about()
        text = found["report"]

        for mark in (app_info.NAME, app_info.VERSION, self.home,
                     media_tools.FFMPEG):
            with self.subTest(mark=mark):
                self.assertIn(mark, text)

    def test_the_screen_has_a_copy_button_that_uses_it(self):
        from app.routers import studio

        page = studio.studio_page().body.decode("utf-8")

        self.assertIn("/studio/api/about", page)
        self.assertIn("정보 복사", page)


class ReadmeTest(unittest.TestCase):
    """설치 안내가 베타 사용자에게 필요한 것을 말한다."""

    def test_the_readme_tells_a_beta_user_what_to_do(self):
        sys.path.insert(0, os.path.join(REPO, "packaging"))

        import release

        readme = release.readme()

        # 막혔을 때 갈 곳 셋.
        for mark in (app_info.CONTACT,
                     runtime_paths.FEEDBACK_DIRNAME,
                     error_log.DIRNAME,
                     "정보 복사"):
            with self.subTest(mark=mark):
                self.assertIn(mark, readme)


if __name__ == "__main__":
    unittest.main()
