"""
EPIC Instagram Connector (Production) (RED->GREEN) -
app/providers/upload/instagram_oauth_service.py.

실제 Meta Business Login for Instagram 흐름(2026년 기준, Meta 공식
문서/실사용 사례로 확인)을 그대로 구현한다 - 브라우저/HTTP 콜백 서버/
Network는 전부 Mock 처리한다(진짜 로그인은 실제 Meta 앱이 있어야
가능하다 - 이 Epic 범위 밖).

엔드포인트가 실제 API 그대로인지가 이 테스트의 핵심이다 - 추측하지
않았다는 것을 URL 문자열 자체로 증명한다.
"""

import os
import sys
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.upload.oauth_service import OAuthError

_MODULE = "app.providers.upload.instagram_oauth_service"

DEFAULT_ACCOUNT_ID = "default"


def _service(**overrides):
    from app.providers.upload.instagram_oauth_service import InstagramOAuthService

    kwargs = {
        "client_id": "app-id", "client_secret": "app-secret",
        "redirect_uri": "http://localhost:8551/callback",
        "callback_timeout_seconds": 0.05,
    }
    kwargs.update(overrides)
    return InstagramOAuthService(**kwargs)


def _mock_http_server_yielding(code=None, error=None):
    """HTTPServer(...)가 생성되자마자 handle_request() 첫 호출에서
    바로 code/error를 "받은 것"처럼 흉내낸다 - 실제 소켓을 열지 않는다."""

    def _factory(*args, **kwargs):
        instance = MagicMock()
        instance.received_code = None
        instance.received_error = None

        def _handle_request():
            instance.received_code = code
            instance.received_error = error

        instance.handle_request.side_effect = _handle_request
        return instance

    return _factory


class TestInstagramOAuthServiceRedirectPortDerivation(unittest.TestCase):
    """Callback Server 실행 조사 - 실제 재현된 버그: redirect_uri가
    ngrok 같은 HTTPS 터널 URL(예: https://xxx.ngrok-free.dev/callback,
    포트 없음)이면 urlparse(redirect_uri).port는 None이다. 기존 코드는
    이때 HTTP의 범용 기본 포트인 80으로 로컬 콜백 서버를 띄웠다 - 이
    프로젝트가 실제로 항상 쓰는 로컬 포트(8551, _DEFAULT_REDIRECT_URI/
    Setup Wizard 기본값과 동일)가 아니다. ngrok은 사용자가 실제로
    "http://localhost:8551"로 포워딩하도록 설정했으므로(ngrok 로그로
    직접 확인됨), 로컬 서버가 80에 떠 있으면 8551은 아무도 안 듣는
    상태(LISTEN 없음) - Meta 콜백이 ngrok까지는 도착해도 502 Bad
    Gateway로 끝난다(실제 재현됨)."""

    def test_explicit_redirect_port_always_wins(self):
        from app.providers.upload.instagram_oauth_service import InstagramOAuthService

        service = InstagramOAuthService(
            client_id="cid", client_secret="secret",
            redirect_uri="https://example.ngrok-free.dev/callback",
            redirect_port=9000,
        )

        self.assertEqual(service.redirect_port, 9000)

    def test_port_embedded_in_redirect_uri_is_used_when_no_explicit_override(self):
        from app.providers.upload.instagram_oauth_service import InstagramOAuthService

        service = InstagramOAuthService(
            client_id="cid", client_secret="secret",
            redirect_uri="http://localhost:9999/callback",
        )

        self.assertEqual(service.redirect_port, 9999)

    def test_redirect_uri_without_a_port_falls_back_to_the_projects_own_default_port(self):
        """실제 버그 재현 - ngrok/실제 프로덕션 HTTPS URL은 거의 항상
        포트를 명시하지 않는다(:443이 암묵적). 이 경우 로컬 서버는
        HTTP의 범용 기본값(80)이 아니라, 이 프로젝트가 실제로 쓰는
        로컬 콜백 포트(8551)로 떠야 한다."""
        from app.providers.upload.instagram_oauth_service import InstagramOAuthService

        service = InstagramOAuthService(
            client_id="cid", client_secret="secret",
            redirect_uri="https://halogen-duly-limeade.ngrok-free.dev/callback",
        )

        self.assertEqual(service.redirect_port, 8551)


class TestInstagramOAuthServiceLogsTheRealAuthorizeUrl(unittest.TestCase):
    """Redirect URI 확인 조사 - "화면엔 ngrok 주소가 보이는데 실제
    authorize URL은 무엇을 쓰는지 로그로 확인해달라"는 요청. authorize
    URL을 실제로 생성한 직후, 브라우저를 열기 전에 그 값을 그대로
    로그로 남긴다 - 지어낸 값이 아니라 실제로 Meta에 보내는 문자열
    그대로."""

    @patch(f"{_MODULE}.requests.get")
    @patch(f"{_MODULE}.requests.post")
    @patch(f"{_MODULE}.HTTPServer")
    @patch(f"{_MODULE}.webbrowser.open")
    def test_logs_the_full_authorize_url_before_opening_the_browser(
        self, mock_open, mock_http_server_cls, mock_post, mock_get,
    ):
        mock_http_server_cls.side_effect = _mock_http_server_yielding(code="auth-code-123")
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"access_token": "short-lived"},
        )
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "long-lived", "expires_in": 5184000},
        )
        service = _service(redirect_uri="https://halogen-duly-limeade.ngrok-free.dev/callback")

        with self.assertLogs(_MODULE, level="INFO") as captured:
            service.authenticate(DEFAULT_ACCOUNT_ID)

        logged = "\n".join(captured.output)
        self.assertIn("https://api.instagram.com/oauth/authorize?", logged)
        self.assertIn("halogen-duly-limeade.ngrok-free.dev%2Fcallback", logged)


class TestInstagramOAuthServiceAuthenticate(unittest.TestCase):

    @patch(f"{_MODULE}.requests.get")
    @patch(f"{_MODULE}.requests.post")
    @patch(f"{_MODULE}.HTTPServer")
    @patch(f"{_MODULE}.webbrowser.open")
    def test_logs_token_exchange_result_without_leaking_the_raw_secret(
        self, mock_open, mock_http_server_cls, mock_post, mock_get,
    ):
        """access_token 교환 결과 확인 조사 - 실제로 교환이 일어났는지
        로그로 확인할 수 있어야 하지만, 실제 access_token 원문을 그대로
        로그 파일에 남기면 그 자체가 자격 증명 유출이 된다(로그 파일은
        디스크에 평문으로 남는다) - 마스킹된 형태(앞 8자...뒤 4자)로만
        남긴다."""
        mock_http_server_cls.side_effect = _mock_http_server_yielding(code="auth-code-123")
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"access_token": "short-lived-secret-value"},
        )
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "IGAAZA1abcdefghijklmnopqrstuvwxyzMHNB", "expires_in": 5184000,
            },
        )

        with self.assertLogs(_MODULE, level="INFO") as captured:
            _service().authenticate(DEFAULT_ACCOUNT_ID)

        logged = "\n".join(captured.output)
        self.assertIn("expires_in=5184000", logged)
        self.assertIn("IGAAZA1a", logged)
        self.assertIn("MHNB", logged)
        self.assertNotIn("IGAAZA1abcdefghijklmnopqrstuvwxyzMHNB", logged)
        self.assertNotIn("short-lived-secret-value", logged)

    @patch(f"{_MODULE}.requests.get")
    @patch(f"{_MODULE}.requests.post")
    @patch(f"{_MODULE}.HTTPServer")
    @patch(f"{_MODULE}.webbrowser.open")
    def test_opens_real_authorize_url_with_correct_params(
        self, mock_open, mock_http_server_cls, mock_post, mock_get,
    ):
        mock_http_server_cls.side_effect = _mock_http_server_yielding(code="auth-code-123")
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"access_token": "short-lived"},
        )
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "long-lived", "expires_in": 5184000},
        )

        _service().authenticate(DEFAULT_ACCOUNT_ID)

        called_url = mock_open.call_args[0][0]
        self.assertTrue(called_url.startswith("https://api.instagram.com/oauth/authorize?"))
        self.assertIn("client_id=app-id", called_url)
        self.assertIn("response_type=code", called_url)
        self.assertIn("instagram_business_basic", called_url)
        self.assertIn("instagram_business_content_publish", called_url)

    @patch(f"{_MODULE}.requests.get")
    @patch(f"{_MODULE}.requests.post")
    @patch(f"{_MODULE}.HTTPServer")
    @patch(f"{_MODULE}.webbrowser.open")
    def test_exchanges_code_for_short_lived_then_long_lived_token(
        self, mock_open, mock_http_server_cls, mock_post, mock_get,
    ):
        mock_http_server_cls.side_effect = _mock_http_server_yielding(code="auth-code-123")
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"access_token": "short-lived"},
        )
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "long-lived", "expires_in": 5184000},
        )

        credential = _service().authenticate(DEFAULT_ACCOUNT_ID)

        post_url = mock_post.call_args[0][0]
        self.assertEqual(post_url, "https://api.instagram.com/oauth/access_token")
        post_data = mock_post.call_args.kwargs["data"]
        self.assertEqual(post_data["code"], "auth-code-123")
        self.assertEqual(post_data["grant_type"], "authorization_code")

        get_url = mock_get.call_args[0][0]
        self.assertEqual(get_url, "https://graph.instagram.com/access_token")
        get_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(get_params["grant_type"], "ig_exchange_token")
        self.assertEqual(get_params["access_token"], "short-lived")

        self.assertEqual(credential.access_token, "long-lived")
        self.assertEqual(credential.account_id, DEFAULT_ACCOUNT_ID)
        expected_days = (credential.expires_at - credential.obtained_at).days
        self.assertEqual(expected_days, 60)

    @patch(f"{_MODULE}.HTTPServer")
    @patch(f"{_MODULE}.webbrowser.open")
    def test_user_denies_login_raises_oauth_error(self, mock_open, mock_http_server_cls):
        mock_http_server_cls.side_effect = _mock_http_server_yielding(
            error="access_denied"
        )

        with self.assertRaises(OAuthError):
            _service().authenticate(DEFAULT_ACCOUNT_ID)

    @patch(f"{_MODULE}.HTTPServer")
    @patch(f"{_MODULE}.webbrowser.open")
    def test_no_callback_received_within_timeout_raises_oauth_error(
        self, mock_open, mock_http_server_cls,
    ):
        instance = MagicMock()
        instance.received_code = None
        instance.received_error = None
        instance.handle_request.side_effect = lambda: None  # 응답이 영원히 안 온다.
        mock_http_server_cls.return_value = instance

        with self.assertRaises(OAuthError):
            _service(callback_timeout_seconds=0.02).authenticate(DEFAULT_ACCOUNT_ID)


class TestInstagramOAuthServiceCallbackServerDoesNotBlockIndefinitely(unittest.TestCase):
    """Critical Bug Fix - Setup Wizard "(응답 없음)" 조사 항목 #3("로컬
    콜백 서버가 데드락되는가"). 위 test_no_callback_received_within_
    timeout_raises_oauth_error()는 HTTPServer 자체를 통째로 Mock해서
    handle_request()가 즉시 반환하도록 만들어 두었다 - 그래서 실제
    socket.accept()가 아무 연결도 없을 때 무한정 블로킹할 수 있다는
    진짜 위험은 이 스위트가 지금까지 한 번도 검증한 적이 없었다.

    이 테스트는 HTTPServer를 Mock하지 않는다 - 실제 소켓을 열되(포트
    0 = OS가 빈 포트를 골라준다), 실제로 아무도 접속하지 않는 상황을
    그대로 재현한다. server.timeout이 설정돼 있지 않으면 단 한 번의
    handle_request() 호출 자체가 영원히 블로킹해, 바깥 while 루프의
    "time.time() < deadline" 확인이 다시 평가될 기회조차 없다 -
    callback_timeout_seconds를 짧게 줘도 실제로는 전혀 지켜지지 않는다."""

    @patch(f"{_MODULE}.webbrowser.open")
    def test_returns_within_callback_timeout_when_nobody_ever_connects(self, mock_open):
        service = _service(
            redirect_uri="http://localhost:0/callback",  # 포트 0 - 실제 빈 포트에 바인딩.
            callback_timeout_seconds=1.0,
        )

        start = time.monotonic()
        with self.assertRaises(OAuthError):
            service.authenticate(DEFAULT_ACCOUNT_ID)
        elapsed = time.monotonic() - start

        # server.timeout이 없으면 handle_request()가 무한 대기하므로 이
        # assert가 실제 버그에서는 절대 통과하지 못한다(Test가 끝나지
        # 않는다) - 고정된 상한(넉넉히 timeout의 3배)으로 "무한 대기가
        # 아니다"를 직접 증명한다.
        self.assertLess(elapsed, service.callback_timeout_seconds * 3)


class TestInstagramOAuthServiceRefresh(unittest.TestCase):

    def _credential(self):
        from app.providers.upload.instagram_credential import InstagramCredential
        now = datetime.now(timezone.utc)
        return InstagramCredential(
            account_id=DEFAULT_ACCOUNT_ID, access_token="old-token",
            obtained_at=now, expires_at=now,
        )

    @patch(f"{_MODULE}.requests.get")
    def test_refresh_uses_real_endpoint_and_updates_expiry(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "refreshed-token", "expires_in": 5184000},
        )

        refreshed = _service().refresh(self._credential())

        called_url = mock_get.call_args[0][0]
        self.assertEqual(called_url, "https://graph.instagram.com/refresh_access_token")
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["grant_type"], "ig_refresh_token")
        self.assertEqual(params["access_token"], "old-token")
        self.assertEqual(refreshed.access_token, "refreshed-token")

    @patch(f"{_MODULE}.requests.get")
    def test_refresh_failure_raises_oauth_error(self, mock_get):
        mock_get.return_value = MagicMock(status_code=400, text="invalid token")

        with self.assertRaises(OAuthError):
            _service().refresh(self._credential())


class TestInstagramOAuthServiceFetchChannelInfo(unittest.TestCase):

    def _credential(self):
        from app.providers.upload.instagram_credential import InstagramCredential
        now = datetime.now(timezone.utc)
        return InstagramCredential(
            account_id=DEFAULT_ACCOUNT_ID, access_token="tok", obtained_at=now, expires_at=now,
        )

    @patch(f"{_MODULE}.requests.get")
    def test_fetch_uses_real_me_endpoint(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"id": "1789", "username": "wellbeingplant"},
        )

        info = _service().fetch_channel_info(self._credential())

        called_url = mock_get.call_args[0][0]
        self.assertEqual(called_url, "https://graph.instagram.com/me")
        self.assertEqual(info.channel_title, "wellbeingplant")
        self.assertEqual(info.account_id, DEFAULT_ACCOUNT_ID)
        self.assertEqual(info.ig_user_id, "1789")

    @patch(f"{_MODULE}.requests.get")
    def test_fetch_failure_raises_oauth_error(self, mock_get):
        mock_get.return_value = MagicMock(status_code=401, text="expired")

        with self.assertRaises(OAuthError):
            _service().fetch_channel_info(self._credential())


if __name__ == "__main__":
    unittest.main()
