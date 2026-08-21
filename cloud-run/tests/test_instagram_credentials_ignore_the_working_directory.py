"""
Sprint256 - Instagram 도 같은 자격증명을 본다.

무엇이 남아 있었나
------------------
Sprint255 가 YouTube 에서 고친 것과 같은 결함이 Instagram 에 그대로
있었다. 로그인은 credential_paths 를 쓰는데 올리는 쪽만 상대 경로를
들고 있었다.

    로그인   instagram_oauth_manager      -> credential_paths.resolve()
    업로드   instagram_upload_step_service -> "credentials/..."
    조립     publishing/instagram_adapter  -> "credentials/..."
    런타임   real_instagram_runtime        -> "credentials/..."  (환경변수도 안 봄)

넷이 각자 정하고 있었다. 켠 자리(cwd)를 따라가므로, 화면에서 로그인한
토큰과 일꾼이 읽는 토큰이 서로 다른 파일이 될 수 있다.

YouTube 에서는 그것이 실제로 일어났다 - Sprint254 의 업로드가 두 번
invalid_scope 로 죽었고, 원인은 저장소가 둘로 갈린 것이었다. Instagram
은 아직 자격증명이 없어 드러나지 않았을 뿐, 생기는 순간 같은 일이 난다.

실제로 어느 길로 가는가
-----------------------
고치는 자리를 하나라도 빠뜨리면 반쪽이 된다. 실제 실행은 이렇게 흐른다.

    instagram_upload_step_service
      -> InstagramAdapter(runtime 없이)
          -> _build_default_runtime()
              -> InstagramTokenStore(storage_path=...)   <- 여기가 진짜다

그래서 이 시험은 함수 하나씩이 아니라 **그 길 끝에서 실제로 열리는
파일**을 본다.

여기서 재지 않는 것
-------------------
실제 로그인도, 실제 Graph API 도 부르지 않는다. 있는 파일은 읽지도
옮기지도 않는다.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import runtime_paths
from app.services import credential_paths

TOKENS = "instagram_oauth_tokens.json"
TOKEN_ENV = "INSTAGRAM_OAUTH_TOKEN_STORE_PATH"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Clean(unittest.TestCase):

    def setUp(self):
        self.was = os.getcwd()
        self.addCleanup(os.chdir, self.was)

        keep = patch.dict(os.environ, {}, clear=False)
        keep.start()
        self.addCleanup(keep.stop)

        for name in (TOKEN_ENV, runtime_paths.HOME_ENV):
            os.environ.pop(name, None)

    def elsewhere(self):
        where = tempfile.mkdtemp()
        self.addCleanup(
            lambda: __import__("shutil").rmtree(where, ignore_errors=True))

        return where

    # -- 네 자리가 각각 어디를 가리키는가 ---------------------------
    def step_path(self):
        from app.services import instagram_upload_step_service as step

        return step._token_store_path()

    def adapter_path(self):
        from app.services.publishing import instagram_adapter

        return instagram_adapter._default_token_store_path()

    def runtime_store_path(self):
        """
        런타임이 **실제로 열게 될** 파일. 상수가 아니라 만들어진
        저장소에게 묻는다 - 상수만 보면 생성자가 무엇을 쓰는지 놓친다.
        """

        from app.services.real_instagram_runtime import RealInstagramRuntime

        engine = RealInstagramRuntime(client_id="", client_secret="")

        return getattr(engine._token_store, "storage_path", None)

    def real_journey_path(self):
        """
        업로드 걸음이 실제로 지나는 길 끝에서 열리는 파일.

            step -> InstagramAdapter -> _build_default_runtime()
                 -> InstagramTokenStore(storage_path=...)
        """

        from app.services.publishing.instagram_adapter import InstagramAdapter

        adapter = InstagramAdapter(asset_publisher=None)

        return getattr(adapter._runtime._token_store, "storage_path", None)

    def login_path(self):
        return credential_paths.resolve(TOKEN_ENV, TOKENS)

    def every_path(self):
        return {
            "step": self.step_path(),
            "adapter": self.adapter_path(),
            "runtime": self.runtime_store_path(),
            "journey": self.real_journey_path(),
            "login": self.login_path(),
        }


# -- 네 자리가 한 곳을 본다 -------------------------------------------
class EveryPlaceLooksAtTheSameFileTest(_Clean):

    def test_다섯이_같은_자리다(self):
        seen = self.every_path()

        self.assertEqual(len(set(seen.values())), 1, seen)

    def test_로그인과_업로드가_같다(self):
        self.assertEqual(self.step_path(), self.login_path())

    def test_실제_길_끝이_업로드_걸음과_같다(self):
        """
        여기가 이번 Sprint 의 핵심이다. step 만 고치고 adapter 를
        놓치면 실제로 열리는 파일은 여전히 다른 것이 된다.
        """

        self.assertEqual(self.real_journey_path(), self.step_path())

    def test_런타임_기본_저장소도_같다(self):
        self.assertEqual(self.runtime_store_path(), self.step_path())


# -- 켠 자리를 따라가지 않는다 ----------------------------------------
class TheWorkingDirectoryDoesNotDecideTest(_Clean):

    def test_어디서_켜도_같은_자리다(self):
        os.chdir(REPO_ROOT)
        here = self.every_path()

        os.chdir(self.elsewhere())
        there = self.every_path()

        for name in here:
            with self.subTest(place=name):
                self.assertEqual(here[name], there[name])

    def test_전부_절대경로다(self):
        os.chdir(self.elsewhere())

        for name, path in self.every_path().items():
            with self.subTest(place=name):
                self.assertTrue(os.path.isabs(path), f"{name}: {path}")

    def test_저장소_안을_가리킨다(self):
        """개발 중에는 저장소의 credentials/ 를 쓴다(있으므로)."""

        os.chdir(self.elsewhere())

        self.assertEqual(
            os.path.normcase(self.step_path()),
            os.path.normcase(os.path.join(REPO_ROOT, "credentials", TOKENS)))


# -- 사람이 정한 것이 이긴다 ------------------------------------------
class WhatThePersonPointsAtWinsTest(_Clean):

    def test_환경변수가_모든_자리를_정한다(self):
        given = os.path.join(self.elsewhere(), "내가 정한.json")

        with patch.dict(os.environ, {TOKEN_ENV: given}):
            seen = self.every_path()

        for name, path in seen.items():
            with self.subTest(place=name):
                self.assertEqual(path, given)

    def test_환경변수는_켠_자리와_무관하다(self):
        given = os.path.join(self.elsewhere(), "내가 정한.json")

        with patch.dict(os.environ, {TOKEN_ENV: given}):
            os.chdir(self.elsewhere())

            self.assertEqual(self.real_journey_path(), given)


# -- 묶인 프로그램 ----------------------------------------------------
class TheFrozenProgramUsesTheUserHomeTest(_Clean):

    def test_저장소에_없으면_사용자_자리다(self):
        home = self.elsewhere()

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
            with patch.object(credential_paths, "repo_dir",
                              return_value=os.path.join(home, "없는자리")):
                seen = self.every_path()

        for name, path in seen.items():
            with self.subTest(place=name):
                self.assertTrue(path.startswith(home), f"{name}: {path}")
                self.assertEqual(os.path.basename(path), TOKENS)

    def test_home_을_바꾸면_따라간다(self):
        first, second = self.elsewhere(), self.elsewhere()
        seen = []

        for home in (first, second):
            with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
                with patch.object(credential_paths, "repo_dir",
                                  return_value=os.path.join(home, "없는자리")):
                    seen.append(self.real_journey_path())

        self.assertTrue(seen[0].startswith(first))
        self.assertTrue(seen[1].startswith(second))


# -- 상대 경로가 남지 않았다 ------------------------------------------
class NoRelativePathIsLeftBehindTest(unittest.TestCase):

    def test_업로드_코드에_상대경로가_없다(self):
        import re

        from app.services import instagram_upload_step_service as step
        from app.services import real_instagram_runtime as rt
        from app.services.publishing import instagram_adapter

        for module in (step, rt, instagram_adapter):
            with open(module.__file__, encoding="utf-8") as f:
                text = re.sub(r'"""[\s\S]*?"""', "", f.read())

            doing = "\n".join(
                line.split("#")[0] for line in text.splitlines()
                if not line.lstrip().startswith("#"))

            with self.subTest(module=module.__name__):
                self.assertNotIn("credentials/instagram", doing)

    def test_옮기거나_지우지_않는다(self):
        import re

        from app.services import instagram_upload_step_service as step
        from app.services import real_instagram_runtime as rt
        from app.services.publishing import instagram_adapter

        for module in (step, rt, instagram_adapter):
            with open(module.__file__, encoding="utf-8") as f:
                text = re.sub(r'"""[\s\S]*?"""', "", f.read())

            for word in ("shutil.move", "shutil.copy", "os.remove",
                         "os.unlink", "os.rename"):
                with self.subTest(module=module.__name__, word=word):
                    self.assertNotIn(word, text)


# -- 다른 것은 그대로 -------------------------------------------------
class TheRestIsUnchangedTest(unittest.TestCase):

    def test_Adapter_계약이_그대로다(self):
        import inspect

        from app.services.publishing.instagram_adapter import InstagramAdapter

        names = list(
            inspect.signature(InstagramAdapter.__init__).parameters)

        self.assertEqual(names[:5], ["self", "asset_publisher",
                                     "poll_interval_seconds",
                                     "poll_timeout_seconds", "runtime"])

    def test_YouTube_자리는_건드리지_않았다(self):
        from app.services import youtube_upload_step_service as yt

        self.assertEqual(yt._TOKEN_STORE_FILENAME, "youtube_oauth_tokens.json")

    def test_TikTok_자리는_건드리지_않았다(self):
        from app.providers.upload import tiktok_oauth_service

        self.assertIn("video.publish", tiktok_oauth_service.SCOPES)

    def test_정책_자체는_그대로다(self):
        """credential_paths 는 이번에 바꾸지 않는다."""

        self.assertTrue(os.path.isabs(credential_paths.repo_dir()))
        self.assertEqual(os.path.basename(credential_paths.repo_dir()),
                         "credentials")


if __name__ == "__main__":
    unittest.main()
