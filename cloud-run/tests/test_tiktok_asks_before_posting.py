"""
Sprint248-A - 올리기 전에 그 계정에 물어본다.

무엇이 빠져 있었나
------------------
두 가지다.

1. 로그인이 받아 오는 권한이 user.info.basic 하나였다. 그것으로는
   누구인지만 알 뿐 올릴 수 없다. Sprint217 이 "계정 연결" 만 하려고
   일부러 좁게 잡았고(그 자리에 그렇게 적혀 있다), Sprint235 가
   올리는 자리를 만들면서 넓히지 않았다.

2. Direct Post 는 init 전에 creator_info 를 묻게 되어 있다. 공식
   문서가 "privacy_level 은 그 응답의 privacy_level_options 중
   하나여야 한다" 고 적는다. 우리는 묻지 않고 바로 init 으로 갔다.

왜 이것이 안전 문제인가
-----------------------
심사를 통과하지 않은 앱은 비공개로만 올릴 수 있다. 그래서 우리는
SELF_ONLY 를 보낸다. 그런데 그 계정이 SELF_ONLY 를 허용하지 않는
경우가 있을 수 있고, 그때 조용히 다른 값으로 바꾸면 **의도하지 않은
공개 게시**가 된다.

그러니 물어보고, 없으면 올리지 않는다. 바꾸지 않고 멈춘다.

여기서 재는 것
--------------
실제 TikTok 은 한 번도 부르지 않는다. requests 를 통째로 감시자로
바꿔 두고 **어느 주소가 몇 번 불렸는가**만 센다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.upload import tiktok_oauth_service
from app.services import real_tiktok_runtime as runtime
from app.services.publishing_runtime_protocol import NonRetryableRuntimeError


class _Response:

    def __init__(self, payload=None, status_code=200):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)
        self.headers = {}

    def json(self):
        return self._payload


def _ok(options=("SELF_ONLY",), duration=None):
    data = {"privacy_level_options": list(options)}

    if duration is not None:
        data["max_video_post_duration_sec"] = duration

    return _Response({"data": data, "error": {"code": "ok"}})


def _init_ok():
    return _Response({"data": {"publish_id": "pid-1",
                               "upload_url": "https://upload.example/x"}})


class _Calls:
    """어느 주소가 몇 번 불렸는가. 바깥으로는 나가지 않는다."""

    def __init__(self):
        self.posts = []
        self.puts = []
        self.creator_reply = _ok()
        self.init_reply = _init_ok()

    def post(self, url, **kwargs):
        self.posts.append(url)

        if url == runtime.CREATOR_INFO_URL:
            reply = self.creator_reply

            if isinstance(reply, Exception):
                raise reply

            return reply

        if url == runtime.INIT_URL:
            return self.init_reply

        return _Response({})

    def put(self, url, **kwargs):
        self.puts.append(url)

        return _Response({}, status_code=200)

    def counted(self, url):
        return self.posts.count(url)


class _Case(unittest.TestCase):

    def setUp(self):
        self.calls = _Calls()

        p = patch.object(runtime, "requests")
        mock = p.start()
        self.addCleanup(p.stop)
        mock.post = self.calls.post
        mock.put = self.calls.put

        self.engine = runtime.RealTikTokRuntime(
            client_key="k", client_secret="s")

        self.video = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "app", "main.py")

    def upload(self):
        return self.engine.upload_media(
            credential=_Credential(), video_url=self.video, caption="제목")

    def inits(self):
        return self.calls.counted(runtime.INIT_URL)

    def asks(self):
        return self.calls.counted(runtime.CREATOR_INFO_URL)


class _Credential:
    access_token = "token"
    refresh_token = "refresh"
    account_id = "default"


# -- 1. 권한 ---------------------------------------------------------
class TheLoginAsksForPermissionToPostTest(unittest.TestCase):

    def test_video_publish_가_들어_있다(self):
        self.assertIn("video.publish", tiktok_oauth_service.SCOPES)

    def test_누구인지도_계속_묻는다(self):
        """이름과 사진은 화면이 쓴다 - 하나로 바꾸면 그것이 사라진다."""

        self.assertIn("user.info.basic", tiktok_oauth_service.SCOPES)

    def test_쉼표로_나눈다(self):
        parts = [p for p in tiktok_oauth_service.SCOPES.split(",") if p]

        self.assertEqual(len(parts), len(set(parts)), "같은 권한이 두 번")
        self.assertTrue(all(p == p.strip() for p in parts), "빈칸이 섞였다")


# -- 2·3. 묻고 나서 올린다 -------------------------------------------
class ItAsksBeforeItPostsTest(_Case):

    def test_creator_info_를_init_보다_먼저_부른다(self):
        self.upload()

        order = [u for u in self.calls.posts
                 if u in (runtime.CREATOR_INFO_URL, runtime.INIT_URL)]

        self.assertEqual(order[:2],
                         [runtime.CREATOR_INFO_URL, runtime.INIT_URL])

    def test_허용하면_그대로_올라간다(self):
        got = self.upload()

        self.assertEqual(got, "pid-1")
        self.assertEqual(self.asks(), 1)
        self.assertEqual(self.inits(), 1)

    def test_보내는_privacy_는_여전히_SELF_ONLY_다(self):
        sent = {}

        def watch(url, **kwargs):
            if url == runtime.INIT_URL:
                sent.update(kwargs.get("json") or {})

            return self.calls.post(url, **kwargs)

        with patch.object(runtime.requests, "post", watch):
            self.upload()

        self.assertEqual(sent["post_info"]["privacy_level"],
                         runtime.DEFAULT_PRIVACY)
        self.assertEqual(runtime.DEFAULT_PRIVACY, "SELF_ONLY")


# -- 4. 허용하지 않으면 올리지 않는다 --------------------------------
class ItNeverSwapsThePrivacyTest(_Case):

    def test_SELF_ONLY_가_없으면_올리지_않는다(self):
        self.calls.creator_reply = _ok(options=("PUBLIC_TO_EVERYONE",
                                                "FOLLOWER_OF_CREATOR"))

        with self.assertRaises(NonRetryableRuntimeError):
            self.upload()

        self.assertEqual(self.inits(), 0)
        self.assertEqual(self.calls.puts, [])

    def test_공개로_바꿔_올리지_않는다(self):
        self.calls.creator_reply = _ok(options=("PUBLIC_TO_EVERYONE",))

        try:
            self.upload()
        except NonRetryableRuntimeError:
            pass

        self.assertEqual(self.inits(), 0)

    def test_왜_안_되는지_사람_말로_적는다(self):
        self.calls.creator_reply = _ok(options=("PUBLIC_TO_EVERYONE",))

        try:
            self.upload()
        except NonRetryableRuntimeError as exc:
            said = str(exc)
        else:
            self.fail("막지 않았다")

        self.assertIn("SELF_ONLY", said)
        self.assertNotIn("Traceback", said)


# -- 5·6. 오류이거나 모자라면 올리지 않는다 ---------------------------
class AnUnknownAnswerIsNotAYesTest(_Case):

    def test_오류면_올리지_않는다(self):
        self.calls.creator_reply = _Response(
            {"error": {"code": "scope_not_authorized",
                       "message": "video.publish 없음"}},
            status_code=403)

        with self.assertRaises(Exception):
            self.upload()

        self.assertEqual(self.inits(), 0)

    def test_목록이_없으면_올리지_않는다(self):
        self.calls.creator_reply = _Response({"data": {}})

        with self.assertRaises(NonRetryableRuntimeError):
            self.upload()

        self.assertEqual(self.inits(), 0)

    def test_목록이_비어_있으면_올리지_않는다(self):
        self.calls.creator_reply = _ok(options=())

        with self.assertRaises(NonRetryableRuntimeError):
            self.upload()

        self.assertEqual(self.inits(), 0)

    def test_망가진_응답도_올리지_않는다(self):
        self.calls.creator_reply = _Response(None)

        with self.assertRaises(Exception):
            self.upload()

        self.assertEqual(self.inits(), 0)

    def test_연결이_끊겨도_올리지_않는다(self):
        self.calls.creator_reply = RuntimeError("망이 끊겼다")

        with self.assertRaises(Exception):
            self.upload()

        self.assertEqual(self.inits(), 0)


# -- 길이 (선택 필드) -------------------------------------------------
class TooLongIsRefusedBeforeUploadingTest(_Case):

    def test_계정_한도를_넘으면_올리지_않는다(self):
        self.calls.creator_reply = _ok(duration=5)

        with patch.object(runtime, "_video_seconds", lambda path: 45.0):
            with self.assertRaises(NonRetryableRuntimeError):
                self.upload()

        self.assertEqual(self.inits(), 0)

    def test_한도를_말해_주지_않으면_재지_않는다(self):
        """없는 사실로 막지 않는다."""

        self.calls.creator_reply = _ok()

        got = self.upload()

        self.assertEqual(got, "pid-1")


# -- 7·8. 기존 계약은 그대로 -----------------------------------------
class TheOldContractIsUntouchedTest(_Case):

    def test_FILE_UPLOAD_그대로다(self):
        sent = {}

        def watch(url, **kwargs):
            if url == runtime.INIT_URL:
                sent.update(kwargs.get("json") or {})

            return self.calls.post(url, **kwargs)

        with patch.object(runtime.requests, "post", watch):
            self.upload()

        source = sent["source_info"]

        self.assertEqual(source["source"], "FILE_UPLOAD")
        self.assertEqual(source["total_chunk_count"], 1)
        self.assertEqual(source["video_size"], source["chunk_size"])

    def test_파일을_그대로_밀어_넣는다(self):
        self.upload()

        self.assertEqual(self.calls.puts, ["https://upload.example/x"])

    def test_공개_URL_이_필요_없다는_사실이_그대로다(self):
        self.assertFalse(runtime.RealTikTokRuntime.capabilities
                         .requires_public_url)

    def test_두_걸음_계약이_그대로다(self):
        self.assertTrue(runtime.RealTikTokRuntime.capabilities
                        .two_phase_publish)

    def test_상태_확인은_예전_주소_그대로다(self):
        self.assertEqual(
            runtime.STATUS_URL,
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/")


# -- 9. 바깥으로 나가지 않았다 ---------------------------------------
class NothingLeftThisMachineTest(_Case):

    def test_부른_주소가_전부_공식_주소다(self):
        self.upload()

        for url in self.calls.posts:
            with self.subTest(url=url):
                self.assertTrue(url.startswith("https://open.tiktokapis.com"),
                                url)

    def test_설정이_없으면_묻지도_않는다(self):
        engine = runtime.RealTikTokRuntime(client_key="", client_secret="")

        with self.assertRaises(Exception):
            engine.upload_media(credential=_Credential(),
                                video_url=self.video, caption="제목")

        self.assertEqual(self.asks(), 0)
        self.assertEqual(self.inits(), 0)


if __name__ == "__main__":
    unittest.main()
