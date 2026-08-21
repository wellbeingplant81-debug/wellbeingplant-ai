"""
Sprint255 - 자격증명이 어디서 켰는지에 따라 달라지지 않는다.

무엇이 실제로 있었나
--------------------
Sprint254 의 실제 업로드가 두 번 죽었다.

    OAuthError: Google token refresh failed
    invalid_scope: Bad Request

Sprint251 에서 새 권한(youtube)으로 다시 로그인했는데도 그랬다. 이유는
로그인한 자리와 올리는 자리가 서로 다른 파일을 보고 있었기 때문이다.

    로그인   oauth_manager -> credential_paths.resolve()  -> 옳게 찾음
    업로드   youtube_upload_step_service                  -> "credentials/..."

둘째가 상대 경로다. 켠 자리(cwd)를 따라간다. 그래서 화면에서 로그인한
토큰은 한 곳에, 일꾼이 읽는 토큰은 다른 곳에 있었고, 일꾼 쪽에는 권한이
둘뿐인 옛 토큰이 남아 있었다. 셋을 요구하니 Google 이 거절했다.

Sprint217 이 이미 답을 만들어 두었다
------------------------------------
credential_paths.resolve() 가 순서를 정한다.

    1. 환경 변수              사람이 직접 가리킨 것 - 언제나 이긴다
    2. 저장소의 credentials/  개발 중 · 실제로 있을 때만
    3. 사용자 자리            묶인 프로그램 · 없어도 그 경로를 돌려준다

로그인 쪽은 이것을 쓰고 있었고 업로드 쪽만 쓰지 않았다. 새 규칙을
만드는 것이 아니라, 쓰지 않던 자리가 쓰게 하는 것이다.

둘째 걸음도 cwd 를 탄다
-----------------------
repo_dir() 이 "credentials" 라는 글자를 돌려주었다. 그것도 켠 자리를
따라간다 - 저장소 밖에서 켜면 저장소의 credentials/ 를 보지 못하고
사용자 자리로 흘러간다.

저장소의 자리는 저장소가 어디 있느냐로 정해지는 것이지, 우리가 어디서
켰느냐로 정해지는 것이 아니다.

여기서 재지 않는 것
-------------------
실제 로그인도, 실제 API 도 부르지 않는다. 있는 파일은 읽지도 옮기지도
않는다 - 경로를 어떻게 고르는가만 본다.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import runtime_paths
from app.services import credential_paths

TOKENS = "youtube_oauth_tokens.json"
SECRET = "client_secret.json"

TOKEN_ENV = "YOUTUBE_OAUTH_TOKEN_STORE_PATH"
SECRET_ENV = "YOUTUBE_OAUTH_CLIENT_SECRET_PATH"


class _Clean(unittest.TestCase):
    """이 시험이 켠 자리와 환경을 원래대로 돌려 놓는다."""

    def setUp(self):
        self.was = os.getcwd()
        self.addCleanup(os.chdir, self.was)

        keep = patch.dict(os.environ, {}, clear=False)
        keep.start()
        self.addCleanup(keep.stop)

        for name in (TOKEN_ENV, SECRET_ENV, runtime_paths.HOME_ENV):
            os.environ.pop(name, None)

    def elsewhere(self):
        """저장소가 아닌 자리. 정리는 시험이 끝날 때."""

        where = tempfile.mkdtemp()
        self.addCleanup(
            lambda: __import__("shutil").rmtree(where, ignore_errors=True))

        return where


# -- 저장소 자리는 저장소가 정한다 ------------------------------------
class TheRepoFolderIsWhereTheRepoIsTest(_Clean):

    def test_절대경로다(self):
        self.assertTrue(os.path.isabs(credential_paths.repo_dir()),
                        credential_paths.repo_dir())

    def test_켠_자리를_바꿔도_같다(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        here = credential_paths.repo_dir()

        os.chdir(self.elsewhere())
        there = credential_paths.repo_dir()

        self.assertEqual(here, there)

    def test_그_자리가_실제로_저장소_안이다(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.assertEqual(
            os.path.normcase(credential_paths.repo_dir()),
            os.path.normcase(os.path.join(root, "credentials")))


# -- 업로드가 읽는 자리 -----------------------------------------------
class TheUploadStepAsksTheSamePlaceTest(_Clean):

    def token_path(self):
        from app.services import youtube_upload_step_service as step

        return step.token_store_path()

    def secret_path(self):
        from app.services import youtube_upload_step_service as step

        return step.client_secret_path()

    def test_켠_자리를_바꿔도_토큰_자리가_같다(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        here = self.token_path()

        os.chdir(self.elsewhere())
        there = self.token_path()

        self.assertEqual(here, there)

    def test_켠_자리를_바꿔도_열쇠_자리가_같다(self):
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        here = self.secret_path()

        os.chdir(self.elsewhere())
        there = self.secret_path()

        self.assertEqual(here, there)

    def test_상대경로를_기본값으로_쓰지_않는다(self):
        os.chdir(self.elsewhere())

        for path in (self.token_path(), self.secret_path()):
            with self.subTest(path=path):
                self.assertTrue(os.path.isabs(path), path)

    def test_런타임도_같은_자리를_본다(self):
        """
        일꾼은 step 을 지나고, 화면의 다른 길은 runtime 을 지난다.
        두 길이 다른 파일을 보면 이번 결함이 그대로 되풀이된다.
        """

        from app.services import real_youtube_runtime as rt
        from app.services import youtube_upload_step_service as step

        os.chdir(self.elsewhere())

        self.assertEqual(rt._default_token_store_path(),
                         step.token_store_path())
        self.assertEqual(rt._default_client_secret_path(),
                         step.client_secret_path())


# -- 사람이 정한 것이 이긴다 ------------------------------------------
class WhatThePersonPointsAtWinsTest(_Clean):

    def test_환경변수가_토큰_자리를_정한다(self):
        from app.services import youtube_upload_step_service as step

        given = os.path.join(self.elsewhere(), "내가 정한.json")

        with patch.dict(os.environ, {TOKEN_ENV: given}):
            self.assertEqual(step.token_store_path(), given)

    def test_환경변수가_열쇠_자리를_정한다(self):
        from app.services import youtube_upload_step_service as step

        given = os.path.join(self.elsewhere(), "내가 정한.json")

        with patch.dict(os.environ, {SECRET_ENV: given}):
            self.assertEqual(step.client_secret_path(), given)

    def test_환경변수는_켠_자리와_무관하다(self):
        from app.services import youtube_upload_step_service as step

        given = os.path.join(self.elsewhere(), "내가 정한.json")

        with patch.dict(os.environ, {TOKEN_ENV: given}):
            os.chdir(self.elsewhere())

            self.assertEqual(step.token_store_path(), given)


# -- 사용자 자리 ------------------------------------------------------
class TheUserHomeIsUsedWhenTheRepoHasNoneTest(_Clean):

    def test_저장소에_없으면_사용자_자리다(self):
        """묶인 프로그램의 상황이다 - 번들에는 credentials 가 없다."""

        from app.services import youtube_upload_step_service as step

        home = self.elsewhere()

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
            with patch.object(credential_paths, "repo_dir",
                              return_value=os.path.join(home, "없는자리")):
                where = step.token_store_path()

        self.assertTrue(where.startswith(home), where)
        self.assertEqual(os.path.basename(where), TOKENS)

    def test_home_을_바꾸면_따라간다(self):
        from app.services import youtube_upload_step_service as step

        first, second = self.elsewhere(), self.elsewhere()
        seen = []

        for home in (first, second):
            with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
                with patch.object(credential_paths, "repo_dir",
                                  return_value=os.path.join(home, "없는자리")):
                    seen.append(step.token_store_path())

        self.assertTrue(seen[0].startswith(first))
        self.assertTrue(seen[1].startswith(second))
        self.assertNotEqual(seen[0], seen[1])

    def test_파일이_없어도_자리를_말해_준다(self):
        """화면이 그 경로를 보여 주어야 사람이 어디에 둘지 안다."""

        from app.services import youtube_upload_step_service as step

        home = self.elsewhere()

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
            with patch.object(credential_paths, "repo_dir",
                              return_value=os.path.join(home, "없는자리")):
                where = step.token_store_path()

        self.assertFalse(os.path.exists(where))
        self.assertTrue(os.path.isabs(where))


# -- 아무것도 옮기지 않는다 -------------------------------------------
class NothingIsMovedOrDeletedTest(_Clean):

    def test_경로를_고르는_동안_파일을_만들지_않는다(self):
        from app.services import youtube_upload_step_service as step

        home = self.elsewhere()

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
            with patch.object(credential_paths, "repo_dir",
                              return_value=os.path.join(home, "없는자리")):
                step.token_store_path()
                step.client_secret_path()

        # 폴더를 만들지도, 파일을 놓지도 않았다.
        self.assertEqual(os.listdir(home), [])

    def test_옮기거나_지우는_말이_없다(self):
        """
        migration 을 만들지 않는다. 있는 파일은 있는 자리에 둔다.
        """

        import re

        from app.services import credential_paths as mod
        from app.services import youtube_upload_step_service as step

        for module in (mod, step):
            with open(module.__file__, encoding="utf-8") as f:
                text = re.sub(r'"""[\s\S]*?"""', "", f.read())

            doing = "\n".join(
                line.split("#")[0] for line in text.splitlines()
                if not line.lstrip().startswith("#"))

            for word in ("shutil.move", "shutil.copy", "os.remove",
                         "os.unlink", "os.rename"):
                with self.subTest(module=module.__name__, word=word):
                    self.assertNotIn(word, doing)


# -- 다른 것은 그대로 -------------------------------------------------
class TheRestIsUnchangedTest(_Clean):

    def test_scope_세_개가_그대로다(self):
        from app.providers.upload.google_oauth_service import _YOUTUBE_SCOPES

        self.assertEqual(_YOUTUBE_SCOPES, [
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
        ])

    def test_다른_플랫폼도_이제_같은_정책을_쓴다(self):
        """
        Sprint255 에서는 이 자리가 "Instagram 은 아직 상대 경로다" 를
        확인하고 있었다. 이번 범위가 아니니 모르는 사이에 함께 움직이지
        않도록 잠가 둔 것이었다.

        Sprint256 이 그 결함을 없앴다. 전제가 사라졌으므로 확인하는
        사실도 바뀐다 - 이제는 두 플랫폼이 같은 정책을 쓴다는 것을
        본다. 잠금을 푸는 것이 아니라, 잠그는 대상이 옮겨간 것이다.
        """

        from app.services import instagram_upload_step_service as ig

        self.assertEqual(ig._TOKEN_STORE_FILENAME,
                         "instagram_oauth_tokens.json")
        self.assertTrue(os.path.isabs(ig._token_store_path()))

    def test_토큰_보호_방식이_그대로다(self):
        from app.providers.upload import file_token_store

        with open(file_token_store.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("secret_box", source)


if __name__ == "__main__":
    unittest.main()
