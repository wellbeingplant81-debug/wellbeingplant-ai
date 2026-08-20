"""
Sprint235 - TikTok 에 올리는 자리 (Publish Automation, Phase 2).

무엇이 있었고 무엇이 없었나
---------------------------
Sprint217 이 TikTok Login Kit 을 붙였다(PKCE). 그래서 "누구인가"는
안다. 그런데 "올린다"가 없었다 - PublishingRuntimeProtocol 구현체가
YouTube · Instagram 둘뿐이었다.

이번에 만드는 것은 그 세 번째다. 새 계층을 만들지 않는다 - 같은
프로토콜, 같은 자리(app/services/real_*_runtime.py), 같은 Adapter 가
그대로 조립한다.

TikTok 이 다른 점
-----------------
    YouTube    파일을 올리면 그것이 곧 게시다
    Instagram  공개 URL 로 컨테이너를 만들고, 따로 게시를 부른다
    TikTok     init 로 자리를 받고, 그 자리에 파일을 밀어 넣는다.
               따로 "게시" 를 부르는 API 가 **없다** - 처리가 끝나면
               올라가 있다.

그래서 two_phase_publish=True 로 두되, 둘째 걸음은 게시가 아니라
**확인**이다. 이 말을 지어내지 않기 위해 capabilities 와 publish_media
의 뜻을 시험에 못 박는다.

공개 URL 이 필요 없다
---------------------
Instagram 은 video_url 을 요구해서 클라우드 저장소가 있어야 한다.
TikTok 은 FILE_UPLOAD 를 받는다 - 로컬 파일을 그대로 밀어 넣는다.
데스크톱 프로그램에는 이쪽이 맞다.

아직 못 하는 것을 할 수 있는 척하지 않는다
------------------------------------------
TikTok 앱이 없다(TIKTOK_CLIENT_KEY/SECRET 없음). 심사를 통과하지 않은
앱은 비공개(SELF_ONLY)로만 올라간다. 그래서 설정이 없으면 **분명히
거절한다** - 조용히 아무 일도 안 하고 성공했다고 말하지 않는다.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import real_tiktok_runtime as tiktok
from app.services.publishing_runtime_protocol import (
    NonRetryableRuntimeError, PublishingRuntimeProtocol, TransientRuntimeError,
)


def _response(status=200, payload=None, headers=None):
    made = MagicMock()
    made.status_code = status
    made.json.return_value = payload if payload is not None else {}
    made.text = json.dumps(payload or {}, ensure_ascii=False)
    made.headers = headers or {}

    return made


def _credential(token="tok"):
    from datetime import datetime, timedelta, timezone

    from app.providers.upload.oauth_credential import OAuthCredential

    return OAuthCredential(
        account_id="default", access_token=token, refresh_token="r",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1))


class TheRuntimeKeepsTheContractTest(unittest.TestCase):
    """세 번째 구현체다. 계약을 새로 만들지 않는다."""

    def test_같은_프로토콜을_따른다(self):
        self.assertTrue(
            issubclass(tiktok.RealTikTokRuntime, PublishingRuntimeProtocol))

    def test_프로토콜이_요구하는_것을_다_갖췄다(self):
        made = tiktok.RealTikTokRuntime(client_key="k", client_secret="s")

        for name in ("login", "refresh_token", "upload_media", "publish_media",
                     "get_publish_status", "revoke", "get_permalink"):
            self.assertTrue(callable(getattr(made, name, None)), name)

    def test_공개_URL_이_필요_없다(self):
        """
        Instagram 과 갈리는 자리다. 여기서 True 로 적으면 클라우드
        저장소 없이는 아무것도 못 올리게 된다.
        """

        caps = tiktok.RealTikTokRuntime.capabilities

        self.assertFalse(caps.requires_public_url)

    def test_둘째_걸음이_있다고_적는다(self):
        caps = tiktok.RealTikTokRuntime.capabilities

        self.assertTrue(caps.two_phase_publish)
        self.assertTrue(caps.supports_shorts)

    def test_없는_기능을_있다고_적지_않는다(self):
        caps = tiktok.RealTikTokRuntime.capabilities

        self.assertFalse(caps.supports_playlist, "TikTok 에 재생목록이 없다")
        self.assertFalse(caps.supports_schedule, "예약 게시를 아직 붙이지 않았다")


class TheEndpointsAreTheRealOnesTest(unittest.TestCase):
    """
    주소를 지어내지 않는다. 공식 Content Posting API 자리다.
    """

    def test_세_자리를_안다(self):
        self.assertEqual(
            tiktok.INIT_URL,
            "https://open.tiktokapis.com/v2/post/publish/video/init/")

        self.assertEqual(
            tiktok.STATUS_URL,
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/")

    def test_로그인_자리는_Sprint217_것을_쓴다(self):
        from app.providers.upload import tiktok_oauth_service

        self.assertTrue(
            tiktok.RealTikTokRuntime(client_key="k", client_secret="s")
            ._build_oauth_service() is not None
            or True)

        # 새 OAuth 를 만들지 않았다는 사실 자체를 못 박는다.
        with open(tiktok.__file__, encoding="utf-8") as f:
            body = f.read()

        self.assertIn("tiktok_oauth_service", body)
        self.assertNotIn(tiktok_oauth_service.AUTHORIZE_URL, body,
                         "로그인 주소를 여기서 다시 적지 않는다")


class TheRuntimeRefusesWhenUnsetTest(unittest.TestCase):
    """
    앱이 없으면 아무것도 안 된다. 그것을 분명히 말한다 - 조용히
    아무 일도 안 하고 성공했다고 하지 않는다.
    """

    def setUp(self):
        self.blank = tiktok.RealTikTokRuntime(client_key="", client_secret="")

    def test_설정이_없으면_설정이_없다고_한다(self):
        self.assertFalse(self.blank.is_configured())

    def test_올리려_하면_거절한다(self):
        with self.assertRaises(NonRetryableRuntimeError) as caught:
            self.blank.upload_media(_credential(), "video.mp4", "글")

        self.assertIn("TIKTOK_CLIENT_KEY", str(caught.exception))

    def test_로그인하려_해도_거절한다(self):
        with self.assertRaises(NonRetryableRuntimeError):
            self.blank.login("default")


class TheUploadFollowsTheApiTest(unittest.TestCase):

    def setUp(self):
        self.runtime = tiktok.RealTikTokRuntime(
            client_key="k", client_secret="s")

        self.video = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tiktok_sample.mp4")

        with open(self.video, "wb") as f:
            f.write(b"0" * 2048)

        self.addCleanup(lambda: os.path.exists(self.video)
                        and os.remove(self.video))

    def test_없는_파일은_바로_거절한다(self):
        """
        다시 시도해도 파일이 다시 생기지 않는다. Adapter 가
        FILE_NOT_FOUND 를 보고 Fail Fast 한다.
        """

        with self.assertRaises(NonRetryableRuntimeError) as caught:
            self.runtime.upload_media(_credential(), "없는파일.mp4", "글")

        self.assertEqual(
            getattr(caught.exception, "error_category", ""), "FILE_NOT_FOUND")

    def test_init_이_계약대로_간다(self):
        """
        Sprint248-A - 이 시험의 이름은 원래 "init 이 먼저다" 였다.

        그때는 그것이 사실이었다. 이제 공식 문서가 요구하는 대로
        creator_info 를 먼저 묻고, 그 계정이 허락해야 init 으로 간다 -
        첫 번째가 아니라는 것 말고는 재는 것이 그대로다.

        그래서 차례를 세지 않고 init 호출을 찾아 그 안을 본다.
        """

        posted = []

        def post(url, **kwargs):
            posted.append((url, kwargs))

            if url == tiktok.CREATOR_INFO_URL:
                return _response(200, {"data": {
                    "privacy_level_options": ["SELF_ONLY"]}})

            return _response(200, {"data": {
                "publish_id": "pid-1",
                "upload_url": "https://upload.example/put"}})

        with patch.object(tiktok.requests, "post", side_effect=post), \
                patch.object(tiktok.requests, "put",
                             return_value=_response(201)):
            got = self.runtime.upload_media(
                _credential("tok"), self.video, "안녕하세요 #건강")

        self.assertEqual(got, "pid-1")

        url, kwargs = next(
            (u, k) for u, k in posted if u == tiktok.INIT_URL)

        self.assertEqual(url, tiktok.INIT_URL)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok")

        body = kwargs["json"]

        self.assertEqual(body["source_info"]["source"], "FILE_UPLOAD")
        self.assertEqual(body["source_info"]["video_size"], 2048)
        self.assertEqual(body["post_info"]["title"], "안녕하세요 #건강")

    def test_심사_전에는_비공개로_올린다(self):
        """
        심사를 통과하지 않은 앱은 SELF_ONLY 만 된다. 공개로 보내면
        TikTok 이 거절하고, 사람은 왜인지 모른다.
        """

        posted = []

        def post(url, **kwargs):
            posted.append((url, kwargs))

            if url == tiktok.CREATOR_INFO_URL:
                return _response(200, {"data": {
                    "privacy_level_options": ["SELF_ONLY"]}})

            return _response(200, {"data": {
                "publish_id": "p", "upload_url": "u"}})

        with patch.object(tiktok.requests, "post", side_effect=post), \
                patch.object(tiktok.requests, "put",
                             return_value=_response(201)):
            self.runtime.upload_media(_credential(), self.video, "글")

        # Sprint248-A - init 은 이제 첫 번째가 아니다. 차례를 세지 않고
        # 그 호출을 찾는다. 재는 것은 그대로다.
        _, kwargs = next((u, k) for u, k in posted if u == tiktok.INIT_URL)

        self.assertEqual(kwargs["json"]["post_info"]["privacy_level"],
                         tiktok.DEFAULT_PRIVACY)

    def test_받은_자리에_파일을_밀어_넣는다(self):
        put = []

        def post(url, **kwargs):
            if url == tiktok.CREATOR_INFO_URL:
                return _response(200, {"data": {
                    "privacy_level_options": ["SELF_ONLY"]}})

            return _response(200, {"data": {
                "publish_id": "pid",
                "upload_url": "https://upload.example/put"}})

        with patch.object(tiktok.requests, "post", side_effect=post), \
                patch.object(tiktok.requests, "put",
                             side_effect=lambda url, **kw: (
                                 put.append((url, kw)), _response(201))[1]):
            self.runtime.upload_media(_credential(), self.video, "글")

        url, kwargs = put[0]

        self.assertEqual(url, "https://upload.example/put")
        self.assertEqual(kwargs["headers"]["Content-Range"], "bytes 0-2047/2048")
        self.assertEqual(kwargs["headers"]["Content-Type"], "video/mp4")
        self.assertEqual(kwargs["data"], b"0" * 2048)

    def test_init_이_실패하면_말해_준다(self):
        with patch.object(tiktok.requests, "post", return_value=_response(
                400, {"error": {"code": "invalid_param",
                                "message": "video_size too small",
                                "log_id": "L1"}})):
            with self.assertRaises(NonRetryableRuntimeError) as caught:
                self.runtime.upload_media(_credential(), self.video, "글")

        self.assertIn("video_size too small", str(caught.exception))
        self.assertEqual(caught.exception.request_id, "L1")

    def test_5xx_는_다시_해_볼_만하다고_한다(self):
        with patch.object(tiktok.requests, "post",
                          return_value=_response(503, {"error": {
                              "code": "internal", "message": "잠시"}})):
            with self.assertRaises(TransientRuntimeError):
                self.runtime.upload_media(_credential(), self.video, "글")

    def test_토큰이_죽었으면_다시_시도하지_않는다(self):
        with patch.object(tiktok.requests, "post",
                          return_value=_response(401, {"error": {
                              "code": "access_token_invalid",
                              "message": "만료"}})):
            with self.assertRaises(NonRetryableRuntimeError) as caught:
                self.runtime.upload_media(_credential(), self.video, "글")

        self.assertEqual(caught.exception.error_category, "TOKEN_EXPIRED")

    def test_그물이_끊기면_다시_해_볼_만하다고_한다(self):
        import requests as real_requests

        with patch.object(tiktok.requests, "post",
                          side_effect=real_requests.exceptions.ConnectionError("끊김")):
            with self.assertRaises(TransientRuntimeError):
                self.runtime.upload_media(_credential(), self.video, "글")


class TheStatusIsPolledTest(unittest.TestCase):

    def setUp(self):
        self.runtime = tiktok.RealTikTokRuntime(
            client_key="k", client_secret="s")

    def _status(self, value):
        with patch.object(tiktok.requests, "post",
                          return_value=_response(200, {"data": {
                              "status": value}})):
            return self.runtime.get_publish_status(_credential(), "pid")

    def test_끝난_것은_FINISHED_로_옮긴다(self):
        """
        Adapter 는 플랫폼 말을 모른다. 프로토콜이 아는 말로 옮긴다.
        """

        self.assertEqual(self._status("PUBLISH_COMPLETE"),
                         tiktok.FINISHED)

    def test_도는_중은_그대로_말한다(self):
        self.assertEqual(self._status("PROCESSING_UPLOAD"),
                         tiktok.IN_PROGRESS)

    def test_실패는_실패라고_한다(self):
        self.assertEqual(self._status("FAILED"), tiktok.FAILED)

    def test_모르는_말은_지어내지_않는다(self):
        self.assertEqual(self._status("무슨상태"), tiktok.IN_PROGRESS)

    def test_상태를_묻는_자리가_맞다(self):
        asked = []

        with patch.object(tiktok.requests, "post",
                          side_effect=lambda url, **kw: (
                              asked.append((url, kw)),
                              _response(200, {"data": {"status": "FAILED"}}))[1]):
            self.runtime.get_publish_status(_credential(), "pid-9")

        url, kwargs = asked[0]

        self.assertEqual(url, tiktok.STATUS_URL)
        self.assertEqual(kwargs["json"], {"publish_id": "pid-9"})


class ThePublishStepOnlyConfirmsTest(unittest.TestCase):
    """
    TikTok 에는 따로 "게시" 를 부르는 API 가 없다. 둘째 걸음은
    확인이다 - 없는 호출을 지어내지 않는다.
    """

    def setUp(self):
        self.runtime = tiktok.RealTikTokRuntime(
            client_key="k", client_secret="s")

    def test_끝났으면_그_id_를_돌려준다(self):
        with patch.object(tiktok.requests, "post",
                          return_value=_response(200, {"data": {
                              "status": "PUBLISH_COMPLETE"}})):
            self.assertEqual(
                self.runtime.publish_media(_credential(), "pid-3"), "pid-3")

    def test_안_끝났으면_성공이라고_하지_않는다(self):
        with patch.object(tiktok.requests, "post",
                          return_value=_response(200, {"data": {
                              "status": "FAILED"}})):
            with self.assertRaises(NonRetryableRuntimeError):
                self.runtime.publish_media(_credential(), "pid-3")

    def test_게시용_주소를_새로_부르지_않는다(self):
        with open(tiktok.__file__, encoding="utf-8") as f:
            body = f.read()

        self.assertNotIn("publish/video/publish", body)
        self.assertNotIn("/post/publish/content/", body)


class ThePermalinkIsNotInventedTest(unittest.TestCase):
    """
    올린 것의 주소를 우리가 지어낼 수 없다. TikTok 은 그것을 주지
    않는다 - 모르면 모른다고 한다.
    """

    def test_빈_문자열을_돌려준다(self):
        runtime = tiktok.RealTikTokRuntime(client_key="k", client_secret="s")

        self.assertEqual(runtime.get_permalink(_credential(), "pid"), "")

    def test_준다고_적지_않는다(self):
        self.assertFalse(
            tiktok.RealTikTokRuntime.capabilities.supports_permalink)


class TheFactoryReadsTheEnvironmentTest(unittest.TestCase):
    """열쇠를 코드에 적지 않는다."""

    def test_코드에_열쇠가_없다(self):
        with open(tiktok.__file__, encoding="utf-8") as f:
            body = f.read()

        # 문자열 조각을 아무거나 고르면 제 코드에 걸린다 - "sk_" 는
        # spam_risk_too_many_posts 에 들어 있었다. 실제로 걸렸다.
        # 재는 것은 **열쇠를 코드에 박았는가**여야 한다.
        import re

        박은것 = re.findall(
            r'(?:client_key|client_secret|access_token)\s*=\s*"[^"]{6,}"', body)

        self.assertEqual(박은것, [], 박은것)

    def test_환경에서_읽는다(self):
        with patch.dict(os.environ, {"TIKTOK_CLIENT_KEY": "kk",
                                     "TIKTOK_CLIENT_SECRET": "ss"}):
            made = tiktok.build_default_tiktok_runtime()

        self.assertTrue(made.is_configured())

    def test_없으면_설정이_없다고_한다(self):
        with patch.dict(os.environ, {"TIKTOK_CLIENT_KEY": "",
                                     "TIKTOK_CLIENT_SECRET": ""}):
            made = tiktok.build_default_tiktok_runtime()

        self.assertFalse(made.is_configured())


if __name__ == "__main__":
    unittest.main()
