"""
Sprint257 - TikTok 도 저장해 둔 로그인을 다시 쓴다.

무엇이 빠져 있었나
------------------
런타임이 token_store 를 받아 두기만 하고 한 번도 읽지 않았다.

    real_tiktok_runtime.py:204   self._token_store = token_store   <- 유일한 등장
    login()                      authenticate() 를 곧장 부른다

authenticate() 는 브라우저를 여는 걸음이다. 그래서 일꾼이 TikTok 을
집을 때마다 로그인 창이 뜨려 하고, 사람이 지켜보지 않는 자리라 거기서
멈춘다. 저장된 토큰이 있어도 쓰이지 않고, 만료돼도 갱신되지 않는다.

게다가 build_default_tiktok_runtime() 은 token_store 를 아예 주지
않았다 - 늘 None 이었다.

다른 둘은 이미 옳다
-------------------
    YouTube    get_valid_credential(oauth_service, self._token_store, account_id)
    Instagram  get_valid_credential(oauth_service, self._token_store, account_id)

같은 함수를 부르면 된다. 새 규칙을 만드는 것이 아니다.

get_valid_credential 이 정한 것
-------------------------------
    없으면      authenticate() 하고 저장한다
    만료됐으면  refresh() 하고 저장한다
    아니면      그대로 쓴다

여기서 fallback 을 새로 지어내지 않는다 - 저 셋이 이미 계약이다.

여기서 재는 것
--------------
실제 TikTok 은 부르지 않는다. authenticate() 가 불리면 그 자리에서
터지도록 두고 **몇 번 불렸는가**를 센다.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import runtime_paths
from app.providers.upload.oauth_credential import OAuthCredential
from app.services import credential_paths, real_tiktok_runtime as tiktok

TOKENS = "tiktok_oauth_tokens.json"
TOKEN_ENV = "TIKTOK_OAUTH_TOKEN_STORE_PATH"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _credential(hours=1):
    return OAuthCredential(
        account_id="default", access_token="저장된-토큰",
        refresh_token="저장된-갱신표",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours))


class _Store:
    """세어 보는 저장소. 파일을 건드리지 않는다."""

    def __init__(self, credential=None):
        self.credential = credential
        self.saved = []

    def load(self, account_id):
        return self.credential

    def save(self, credential):
        self.saved.append(credential)
        self.credential = credential


class _Oauth:
    """브라우저를 여는 자리. 불리면 그 사실을 남긴다."""

    def __init__(self, refreshed=None):
        self.authenticated = 0
        self.refreshed = 0
        self._answer = refreshed

    def authenticate(self, account_id):
        self.authenticated += 1

        return _credential()

    def refresh(self, credential):
        self.refreshed += 1

        return self._answer or _credential()


class _Case(unittest.TestCase):

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

    def engine(self, store, oauth):
        made = tiktok.RealTikTokRuntime(
            client_key="k", client_secret="s", token_store=store)

        # 로그인 서비스를 만드는 자리를 가짜로 바꾼다 - 바깥으로 나가지
        # 않으면서 실제 login() 을 그대로 지난다.
        made._build_oauth_service = lambda: oauth

        return made


# -- 저장된 것이 있으면 다시 로그인하지 않는다 ------------------------
class ASavedLoginIsReusedTest(_Case):

    def test_저장된_토큰이_있으면_브라우저를_열지_않는다(self):
        oauth = _Oauth()
        store = _Store(_credential())

        got = self.engine(store, oauth).login("default")

        self.assertEqual(oauth.authenticated, 0, "브라우저를 열었다")
        self.assertEqual(got.access_token, "저장된-토큰")

    def test_저장소를_실제로_읽는다(self):
        oauth = _Oauth()
        store = _Store(_credential())

        self.engine(store, oauth).login("default")

        self.assertEqual(oauth.authenticated + oauth.refreshed, 0)

    def test_다시_저장하지_않는다(self):
        """멀쩡한 것을 다시 쓰지 않는다 - 파일을 건드릴 이유가 없다."""

        store = _Store(_credential())

        self.engine(store, _Oauth()).login("default")

        self.assertEqual(store.saved, [])


# -- 없거나 만료됐으면 예전 길 그대로 ---------------------------------
class TheOldPathStaysForAMissingOrStaleLoginTest(_Case):

    def test_저장된_것이_없으면_로그인한다(self):
        oauth = _Oauth()
        store = _Store(None)

        self.engine(store, oauth).login("default")

        self.assertEqual(oauth.authenticated, 1)
        self.assertEqual(len(store.saved), 1, "받은 것을 저장하지 않았다")

    def test_만료됐으면_갱신한다(self):
        oauth = _Oauth()
        store = _Store(_credential(hours=-1))

        self.engine(store, oauth).login("default")

        self.assertEqual(oauth.refreshed, 1)
        self.assertEqual(oauth.authenticated, 0, "갱신으로 될 것을 다시 물었다")
        self.assertEqual(len(store.saved), 1)

    def test_설정이_없으면_저장소를_보기도_전에_거절한다(self):
        from app.services.publishing_runtime_protocol import (
            NonRetryableRuntimeError,
        )

        oauth = _Oauth()
        store = _Store(_credential())

        made = tiktok.RealTikTokRuntime(client_key="", client_secret="",
                                        token_store=store)
        made._build_oauth_service = lambda: oauth

        with self.assertRaises(NonRetryableRuntimeError):
            made.login("default")

        self.assertEqual(oauth.authenticated, 0)


# -- 기본 조립이 저장소를 준다 ----------------------------------------
class TheDefaultRuntimeCarriesAStoreTest(_Case):

    def built(self):
        return tiktok.build_default_tiktok_runtime()

    def test_저장소가_비어_있지_않다(self):
        self.assertIsNotNone(self.built()._token_store,
                             "None 이면 login 이 저장된 것을 못 읽는다")

    def test_그_저장소가_TikTok_파일을_본다(self):
        where = self.built()._token_store.storage_path

        self.assertEqual(os.path.basename(where), TOKENS)

    def test_화면이_쓰는_자리와_같다(self):
        """
        social_accounts 가 로그인 결과를 적는 그 파일이어야 한다 -
        다르면 화면에서 로그인해도 일꾼이 못 읽는다.
        """

        self.assertEqual(
            self.built()._token_store.storage_path,
            credential_paths.resolve(TOKEN_ENV, TOKENS))

    def test_켠_자리를_바꿔도_같다(self):
        os.chdir(REPO_ROOT)
        here = self.built()._token_store.storage_path

        os.chdir(self.elsewhere())
        there = self.built()._token_store.storage_path

        self.assertEqual(here, there)
        self.assertTrue(os.path.isabs(here), here)

    def test_환경변수가_이긴다(self):
        given = os.path.join(self.elsewhere(), "내가 정한.json")

        with patch.dict(os.environ, {TOKEN_ENV: given}):
            self.assertEqual(self.built()._token_store.storage_path, given)

    def test_묶인_프로그램은_사용자_자리다(self):
        home = self.elsewhere()

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
            with patch.object(credential_paths, "repo_dir",
                              return_value=os.path.join(home, "없는자리")):
                where = self.built()._token_store.storage_path

        self.assertTrue(where.startswith(home), where)

    def test_자리를_고르는_동안_파일을_만들지_않는다(self):
        home = self.elsewhere()

        with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
            with patch.object(credential_paths, "repo_dir",
                              return_value=os.path.join(home, "없는자리")):
                self.built()

        self.assertEqual(os.listdir(home), [])


# -- 실제 길 전체 -----------------------------------------------------
class TheWholeJourneyReusesTheLoginTest(_Case):

    def test_기본_조립부터_login_까지_브라우저가_열리지_않는다(self):
        """
        build_default_tiktok_runtime() -> _token_store -> login()
        -> get_valid_credential() 까지 그대로 지난다. 함수 하나만
        보는 것이 아니라 실제로 만들어지는 길을 본다.
        """

        oauth = _Oauth()

        # 이 PC 에는 TikTok 앱이 없다. 여기서 재는 것은 "저장된 것을
        # 다시 쓰는가" 이므로, 설정이 있다는 전제만 적는다 - 실제
        # 열쇠가 아니라 아무 글자다.
        with patch.dict(os.environ, {"TIKTOK_CLIENT_KEY": "k",
                                     "TIKTOK_CLIENT_SECRET": "s"}):
            made = tiktok.build_default_tiktok_runtime()

        made._build_oauth_service = lambda: oauth

        with patch.object(type(made._token_store), "load",
                          lambda self, account_id: _credential()):
            got = made.login("default")

        self.assertEqual(oauth.authenticated, 0)
        self.assertEqual(got.access_token, "저장된-토큰")


# -- 나머지 계약은 그대로 ---------------------------------------------
class TheUploadContractIsUnchangedTest(unittest.TestCase):

    def test_주소_셋이_그대로다(self):
        self.assertEqual(
            tiktok.CREATOR_INFO_URL,
            "https://open.tiktokapis.com/v2/post/publish/creator_info/query/")
        self.assertEqual(
            tiktok.INIT_URL,
            "https://open.tiktokapis.com/v2/post/publish/video/init/")
        self.assertEqual(
            tiktok.STATUS_URL,
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/")

    def test_비공개로만_올린다(self):
        self.assertEqual(tiktok.DEFAULT_PRIVACY, "SELF_ONLY")

    def test_공개_URL_이_필요_없다(self):
        self.assertFalse(
            tiktok.RealTikTokRuntime.capabilities.requires_public_url)

    def test_두_걸음_계약이_그대로다(self):
        self.assertTrue(
            tiktok.RealTikTokRuntime.capabilities.two_phase_publish)

    def test_video_publish_권한이_그대로다(self):
        from app.providers.upload import tiktok_oauth_service

        self.assertIn("video.publish", tiktok_oauth_service.SCOPES)
        self.assertIn("user.info.basic", tiktok_oauth_service.SCOPES)

    def test_다른_플랫폼을_건드리지_않았다(self):
        from app.services import instagram_upload_step_service as ig
        from app.services import youtube_upload_step_service as yt

        self.assertEqual(yt._TOKEN_STORE_FILENAME, "youtube_oauth_tokens.json")
        self.assertEqual(ig._TOKEN_STORE_FILENAME,
                         "instagram_oauth_tokens.json")


if __name__ == "__main__":
    unittest.main()
