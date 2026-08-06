"""
Sprint97 - Instagram Runtime 이식 (Epic 50, Phase 1).

Sprint89가 Upload Core의 Instagram 3종(credential/oauth_service/
token_store)을 이미 가져왔고, Sprint90이 OAuthManager를, Sprint91이
PublishingRuntimeProtocol을 가져왔다. 이번에는 그 위에 얹히는 Runtime
계층만 옮긴다.

이 스프린트는 실제 업로드도 OAuth 로그인도 금지다. 그것을 지키는
장치가 코드 안에 이미 있다 - RealInstagramRuntime은 Meta App ID/Secret이
없으면 네트워크를 시도하기 전에 먼저 실패한다. 이 저장소에는 그
자격증명이 없으므로, 실수로 무언가 나가는 일이 구조적으로 막혀 있다.

여기 테스트는 requests를 한 번도 실제로 부르지 않는다.
"""

import ast
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.instagram_credential import InstagramCredential
from app.services import instagram_oauth_manager, real_instagram_runtime
from app.services.instagram_runtime import InstagramRuntimeProtocol
from app.services.publishing_runtime_protocol import (
    PublishingRuntimeProtocol,
    TransientRuntimeError,
)
from app.services.real_instagram_runtime import (
    InstagramAPIError,
    RealInstagramRuntime,
    _classify_response_error,
)


def _credential(account_id="default", ig_user_id="ig1"):
    now = datetime.now(timezone.utc)
    credential = InstagramCredential(
        account_id=account_id,
        access_token="token",
        obtained_at=now,
        expires_at=now + timedelta(days=30),
    )
    credential.ig_user_id = ig_user_id
    return credential


class _Response:
    """requests.Response 자리. 실제 네트워크는 없다."""

    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class TestTheProtocolContract(unittest.TestCase):

    def test_it_inherits_the_shared_runtime_protocol(self):
        """Sprint91이 YouTube용으로 옮겨 둔 그 계약이다 - 두 벌을
        만들지 않는다."""

        self.assertTrue(
            issubclass(InstagramRuntimeProtocol, PublishingRuntimeProtocol),
        )

    def test_capabilities_match_what_instagram_actually_does(self):
        caps = InstagramRuntimeProtocol.capabilities

        # Graph API는 Container -> Publish 2단계다. YouTube와 정반대.
        self.assertTrue(caps.two_phase_publish)
        # video_url이 공개 URL이어야 한다 - 로컬 파일 경로가 아니다.
        self.assertTrue(caps.requires_public_url)
        self.assertTrue(caps.supports_permalink)
        # 예약 발행과 재생목록은 Instagram에 없다.
        self.assertFalse(caps.supports_schedule)
        self.assertFalse(caps.supports_playlist)

    def test_it_differs_from_youtube_exactly_where_the_platforms_differ(self):
        from app.services.real_youtube_runtime import RealYouTubeRuntime

        youtube = RealYouTubeRuntime.capabilities
        instagram = InstagramRuntimeProtocol.capabilities

        self.assertNotEqual(youtube.two_phase_publish, instagram.two_phase_publish)
        self.assertNotEqual(youtube.requires_public_url, instagram.requires_public_url)

    def test_the_real_runtime_implements_it(self):
        self.assertTrue(issubclass(RealInstagramRuntime, InstagramRuntimeProtocol))


class TestNothingHappensWithoutMetaCredentials(unittest.TestCase):
    """이 저장소에는 Meta App ID/Secret이 없다. 그것이 이번 스프린트의
    "실제 업로드 금지 / OAuth 로그인 금지"를 코드 수준에서 지킨다."""

    def setUp(self):
        self.runtime = RealInstagramRuntime()

    def test_it_reports_itself_as_not_configured(self):
        self.assertFalse(self.runtime.is_configured())

    def test_every_network_method_refuses_before_touching_the_network(self):
        credential = _credential()

        calls = [
            lambda: self.runtime.login("default"),
            lambda: self.runtime.refresh_token(credential),
            lambda: self.runtime.upload_media(credential, "https://u", "cap"),
            lambda: self.runtime.publish_media(credential, "c1"),
            lambda: self.runtime.get_publish_status(credential, "c1"),
            lambda: self.runtime.get_permalink(credential, "m1"),
        ]

        with patch.object(real_instagram_runtime, "requests") as net:
            for index, call in enumerate(calls):
                with self.subTest(method=index):
                    with self.assertRaises(Exception):
                        call()

            net.post.assert_not_called()
            net.get.assert_not_called()

    def test_login_never_reaches_the_oauth_chain_while_unconfigured(self):
        """login()은 get_valid_credential()을 타고, 그것은 저장된 토큰이
        없으면 브라우저를 연다(Sprint90/91에서 YouTube 쪽에 같은 함정이
        있었다). 설정이 없으면 거기까지 가지 않는다."""

        with patch.object(real_instagram_runtime, "get_valid_credential") as loader:
            with self.assertRaises(Exception):
                self.runtime.login("default")

        loader.assert_not_called()

    def test_revoke_works_without_credentials_because_it_is_local_only(self):
        """Meta에 원격 무효화 API는 없다. 로컬 토큰 삭제가 전부다."""

        deleted = []

        class _Store:
            def delete(self, account_id):
                deleted.append(account_id)

        runtime = RealInstagramRuntime(token_store=_Store())
        runtime.revoke(_credential("acct"))

        self.assertEqual(deleted, ["acct"])


class TestErrorClassificationIsPortedVerbatim(unittest.TestCase):
    """Meta가 실제로 쓰는 오류 코드다. 다시 쓰면 추측이 된다."""

    def test_190_is_token_expired(self):
        self.assertEqual(
            _classify_response_error({"error": {"code": 190}}, 400), "TOKEN_EXPIRED",
        )

    def test_permission_codes(self):
        for code in (10, 200, 210):
            with self.subTest(code=code):
                self.assertEqual(
                    _classify_response_error({"error": {"code": code}}, 403),
                    "PERMISSION_ERROR",
                )

    def test_rate_limit_codes_and_429(self):
        for code in (4, 17, 32, 613):
            with self.subTest(code=code):
                self.assertEqual(
                    _classify_response_error({"error": {"code": code}}, 400),
                    "RATE_LIMIT",
                )

        self.assertEqual(_classify_response_error({}, 429), "RATE_LIMIT")

    def test_the_whole_5xx_range_is_transient(self):
        for status in (500, 501, 503, 505, 599):
            with self.subTest(status=status):
                self.assertEqual(
                    _classify_response_error({}, status), "NETWORK_ERROR",
                )

    def test_anything_else_is_unknown(self):
        self.assertEqual(_classify_response_error({}, 418), "UNKNOWN_ERROR")

    def test_a_malformed_error_body_does_not_raise(self):
        self.assertEqual(_classify_response_error(None, 400), "UNKNOWN_ERROR")
        self.assertEqual(_classify_response_error("not a dict", 400), "UNKNOWN_ERROR")


class TestTheTwoPhasePublishFlow(unittest.TestCase):
    """Container 생성 -> 상태 조회 -> 게시. YouTube와 근본적으로 다른
    부분이라 실제로 태워 본다(네트워크는 갈아끼운다)."""

    def setUp(self):
        self.runtime = RealInstagramRuntime(
            client_id="id", client_secret="secret",
        )
        self.credential = _credential()

    def test_upload_media_creates_a_container_and_returns_its_id(self):
        seen = {}

        def _post(url, data=None, timeout=None):
            seen.update(url=url, data=data)
            return _Response(200, {"id": "container-1"})

        with patch.object(real_instagram_runtime.requests, "post", _post):
            container_id = self.runtime.upload_media(
                self.credential, "https://cdn/v.mp4", "캡션",
            )

        self.assertEqual(container_id, "container-1")
        self.assertIn("/ig1/media", seen["url"])
        self.assertEqual(seen["data"]["media_type"], "REELS")
        self.assertEqual(seen["data"]["video_url"], "https://cdn/v.mp4")

    def test_a_cover_url_is_attached_only_when_given(self):
        seen = {}

        def _post(url, data=None, timeout=None):
            seen.update(data=data)
            return _Response(200, {"id": "c"})

        with patch.object(real_instagram_runtime.requests, "post", _post):
            self.runtime.upload_media(self.credential, "https://v", "cap")
        self.assertNotIn("cover_url", seen["data"])

        with patch.object(real_instagram_runtime.requests, "post", _post):
            self.runtime.upload_media(
                self.credential, "https://v", "cap", cover_url="https://c.png",
            )
        self.assertEqual(seen["data"]["cover_url"], "https://c.png")

    def test_publish_media_returns_the_media_id(self):
        with patch.object(
            real_instagram_runtime.requests, "post",
            lambda *a, **k: _Response(200, {"id": "media-9"}),
        ):
            self.assertEqual(
                self.runtime.publish_media(self.credential, "c1"), "media-9",
            )

    def test_get_publish_status_reads_the_status_code(self):
        with patch.object(
            real_instagram_runtime.requests, "get",
            lambda *a, **k: _Response(200, {"status_code": "FINISHED"}),
        ):
            self.assertEqual(
                self.runtime.get_publish_status(self.credential, "c1"), "FINISHED",
            )

    def test_a_permalink_needs_a_real_lookup_unlike_youtube(self):
        """YouTube는 video_id로 URL을 조립하면 되지만 Instagram은
        조회해야 한다 - 그래서 capabilities가 다르다."""

        with patch.object(
            real_instagram_runtime.requests, "get",
            lambda *a, **k: _Response(200, {"permalink": "https://instagr.am/p/x"}),
        ):
            self.assertEqual(
                self.runtime.get_permalink(self.credential, "m1"),
                "https://instagr.am/p/x",
            )


class TestFailuresAreCarriedNotSwallowed(unittest.TestCase):

    def setUp(self):
        self.runtime = RealInstagramRuntime(client_id="id", client_secret="s")
        self.credential = _credential()

    def test_a_5xx_becomes_a_transient_error(self):
        with patch.object(
            real_instagram_runtime.requests, "post",
            lambda *a, **k: _Response(503, {}, text="down"),
        ):
            with self.assertRaises(TransientRuntimeError):
                self.runtime.upload_media(self.credential, "https://v", "c")

    def test_a_token_error_becomes_an_api_error_with_its_category(self):
        with patch.object(
            real_instagram_runtime.requests, "post",
            lambda *a, **k: _Response(
                400, {"error": {"code": 190, "fbtrace_id": "trace-1"}},
            ),
        ):
            with self.assertRaises(InstagramAPIError) as caught:
                self.runtime.publish_media(self.credential, "c1")

        self.assertEqual(caught.exception.error_category, "TOKEN_EXPIRED")
        self.assertEqual(caught.exception.request_id, "trace-1")

    def test_a_rate_limit_carries_retry_after(self):
        with patch.object(
            real_instagram_runtime.requests, "post",
            lambda *a, **k: _Response(
                429, {"error": {"code": 4}}, headers={"Retry-After": "12"},
            ),
        ):
            with self.assertRaises(InstagramAPIError) as caught:
                self.runtime.publish_media(self.credential, "c1")

        self.assertEqual(caught.exception.retry_after_seconds, 12.0)

    def test_a_network_exception_becomes_transient(self):
        import requests as real_requests

        def _boom(*a, **k):
            raise real_requests.exceptions.ConnectionError("no route")

        with patch.object(real_instagram_runtime.requests, "post", _boom):
            with self.assertRaises(TransientRuntimeError):
                self.runtime.upload_media(self.credential, "https://v", "c")


class TestTheOAuthManagerIsAssembledNotReimplemented(unittest.TestCase):

    def test_it_reuses_the_manager_ported_for_youtube(self):
        from app.services.oauth_manager import OAuthManager

        manager = instagram_oauth_manager.build_default_instagram_oauth_manager()

        self.assertIsInstance(manager, OAuthManager)

    def test_the_paths_are_instagram_specific(self):
        manager = instagram_oauth_manager.build_default_instagram_oauth_manager()

        self.assertIn(
            "instagram", getattr(manager.token_store, "storage_path", ""),
        )

    def test_building_it_touches_no_network(self):
        import urllib.request

        with patch.object(urllib.request, "urlopen") as opener:
            instagram_oauth_manager.build_default_instagram_oauth_manager()

        opener.assert_not_called()

    def test_a_health_check_without_a_token_reports_reauth_required(self):
        """로컬 파일만 읽는다 - 네트워크도 브라우저도 없다."""

        from app.services import oauth_health

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                "INSTAGRAM_OAUTH_TOKEN_STORE_PATH": os.path.join(tmp, "t.json"),
            }):
                manager = (
                    instagram_oauth_manager.build_default_instagram_oauth_manager()
                )
                health = manager.check_health()

        self.assertEqual(health.status, oauth_health.REAUTH_REQUIRED)


class TestNothingDeadWasPorted(unittest.TestCase):
    """"사용되는 모듈만 이식. 죽은 코드 이식 금지."" """

    def test_the_qt_desktop_layer_did_not_come_across(self):
        for module in (real_instagram_runtime, instagram_oauth_manager):
            tree = ast.parse(open(module.__file__, encoding="utf-8").read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                elif isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                for name in names:
                    with self.subTest(module=module.__name__, imported=name):
                        self.assertNotIn("desktop", name)
                        self.assertNotIn("PySide", name)

    def test_the_mock_and_factory_and_adapter_were_not_ported(self):
        """셋 다 이 저장소에서 부를 곳이 없다 - factory는 Qt 설정
        모델을, adapter는 desktop 게시 오케스트레이션을 필요로 한다."""

        services = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "services",
        )

        for name in ("mock_instagram_runtime.py", "instagram_runtime_factory.py",
                     "instagram_adapter.py", "instagram_analytics_connector.py"):
            with self.subTest(name=name):
                self.assertFalse(os.path.exists(os.path.join(services, name)))


class TestNothingElseWasTouched(unittest.TestCase):
    """Acceptance 5, 6 - Video Pipeline 영향 0, YouTube 기능 영향 0."""

    def _imports(self, module):
        """원문을 훑지 않는다.

        YouTube runtime의 설명 주석은 Instagram을 언급한다 - capabilities가
        왜 정반대인지(2단계 게시, 공개 URL) 적어 두었기 때문이다. 문자열로
        찾으면 그 산문에 걸린다. 실제로 의존하는지는 import가 말한다."""

        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                names.update(a.name for a in node.names)
        return names

    def test_the_pipeline_does_not_import_instagram(self):
        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("instagram", name.lower())

    def test_the_youtube_runtime_is_unaffected(self):
        from app.services import real_youtube_runtime

        for name in self._imports(real_youtube_runtime):
            with self.subTest(imported=name):
                self.assertNotIn("instagram", name.lower())

    def test_the_upload_step_still_only_knows_youtube(self):
        from app.services import youtube_upload_step_service

        for name in self._imports(youtube_upload_step_service):
            with self.subTest(imported=name):
                self.assertNotIn("instagram", name.lower())

    def test_no_instagram_endpoint_exists_yet(self):
        """Queue/Workflow/UI 연결은 이번 스프린트 금지 항목이다."""

        from app.main import app

        for path in app.openapi()["paths"]:
            with self.subTest(path=path):
                self.assertNotIn("instagram", path.lower())


if __name__ == "__main__":
    unittest.main()
