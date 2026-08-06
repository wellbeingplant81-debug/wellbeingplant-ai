"""
EPIC Instagram Connector (Production) - Instagram OAuth Service
(Business Login for Instagram, Meta 공식 문서/실사용 사례 기준, 2026).

app.providers.upload.google_oauth_service.GoogleOAuthService(무수정)와
같은 위치의 역할을 하지만, Google과는 근본적으로 다른 흐름이다:

- Google: InstalledAppFlow가 loopback(동적 포트, http://localhost:PORT)
  전체를 대신 처리해 준다.
- Instagram(Meta): 등록된 redirect_uri가 정확히 일치해야 한다(동적 포트
  불가) - 그래서 이 파일이 직접 로컬 콜백 서버(표준 라이브러리
  http.server, 새 pip 패키지 없음)를 띄운다. redirect_uri/포트는 생성자
  인자로 받는다(하드코딩 금지, Google Provider와 동일한 원칙) - 실제
  Meta 앱 대시보드에 등록한 값과 정확히 일치해야 한다.

중요한 실제 제약(추측 아님, Meta 공식 문서 기준) - Meta는 프로덕션에서
HTTPS redirect_uri를 요구한다. 이 파일은 순수 HTTP 로컬 서버만 제공한다
- 로컬 TLS 종단(자체 서명 인증서/리버스 프록시 등)은 이 파일이 대신
해결하지 않는다(환경/운영 설정의 몫이지, 코드로 지어낼 부분이 아니다).
실제 등록 시 redirect_uri를 그에 맞게 구성해야 한다.

토큰 모델도 Google과 다르다(app.providers.upload.instagram_credential
참고) - 별도 refresh_token이 없다. authenticate()는 인가 코드 -> 단기
토큰(1시간) -> 장기 토큰(60일) 순으로 실제로 교환한다. refresh()는 같은
장기 토큰을 연장할 뿐이다.

모든 실패는 app.providers.upload.oauth_service.OAuthError로 통일해
던진다(무수정 재사용) - desktop.application.oauth.OAuthManager가 이미
그 타입만 잡도록 만들어져 있어, 새 예외 처리 경로를 만들지 않아도 된다.
"""

import logging
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from app.providers.upload.instagram_credential import InstagramCredential
from app.providers.upload.oauth_service import OAuthError

logger = logging.getLogger(__name__)


def _mask_token(token: str) -> str:
    # access_token 교환 결과 확인 조사 - 원문을 그대로 로그(디스크에
    # 평문으로 남는 파일)에 남기면 그 자체가 자격 증명 유출이다 - 실제
    # 교환이 일어났는지 확인하는 데 필요한 최소 정보(길이/앞뒤 일부)만
    # 남긴다.
    if not token:
        return "(empty)"
    if len(token) <= 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"

AUTHORIZE_URL = "https://api.instagram.com/oauth/authorize"
SHORT_LIVED_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
LONG_LIVED_EXCHANGE_URL = "https://graph.instagram.com/access_token"
REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
ME_URL = "https://graph.instagram.com/me"

_SCOPES = "instagram_business_basic,instagram_business_content_publish"
_REQUEST_TIMEOUT_SECONDS = 30
_DEFAULT_CALLBACK_TIMEOUT_SECONDS = 300
_CALLBACK_SUCCESS_HTML = (
    "<html><body>로그인이 완료되었습니다. 이 창을 닫아도 됩니다.</body></html>"
)


class InstagramAccountInfo:
    """desktop.application.oauth.OAuthManager와의 duck typing 호환을
    위한 최소 모양이다 - channel_title이라는 필드명은 app.providers.
    upload.channel_info.ChannelInfo(YouTube 전용, 무수정)와 맞춘 것일
    뿐, Instagram에 실제 "Channel" 개념이 있다는 뜻은 아니다.

    ig_user_id는 OAuthManager가 쓰지 않는다 - desktop.application.
    publishing.connectors.instagram_adapter.InstagramAdapter가 실제
    Graph API 엔드포인트(/{ig-user-id}/media 등)를 구성할 때 쓴다."""

    def __init__(self, account_id: str, channel_title: str, ig_user_id: str = ""):
        self.account_id = account_id
        self.channel_title = channel_title
        self.ig_user_id = ig_user_id


class _CallbackHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        self.server.received_code = (query.get("code") or [None])[0]
        self.server.received_error = (
            (query.get("error_description") or query.get("error") or [None])[0]
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_CALLBACK_SUCCESS_HTML.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # GoogleOAuthService와 동일하게 stdout을 스팸하지 않는다.


class InstagramOAuthService:

    def __init__(
        self, client_id: str, client_secret: str, redirect_uri: str,
        redirect_port: int = None,
        callback_timeout_seconds: float = _DEFAULT_CALLBACK_TIMEOUT_SECONDS,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        # Callback Server 실행 조사 - 실제 재현된 버그: ngrok 등 HTTPS
        # 터널 URL은 포트를 명시하지 않는다(:443 암묵적) -
        # urlparse(...).port가 None이 되어, 예전에는 HTTP의 범용 기본
        # 포트(80)로 로컬 콜백 서버가 떴다. 이 프로젝트가 실제로 항상
        # 쓰는 로컬 포트(8551, _DEFAULT_REDIRECT_URI와 동일)로 대신
        # 떨어져야 ngrok이 실제로 포워딩하는 대상과 일치한다.
        self.redirect_port = redirect_port or urlparse(redirect_uri).port or 8551
        self.callback_timeout_seconds = callback_timeout_seconds

    def authenticate(self, account_id: str) -> InstagramCredential:
        try:
            code = self._authorize_and_capture_code()
            short_lived_token = self._exchange_code_for_short_lived_token(code)
            access_token, expires_in = self._exchange_for_long_lived_token(short_lived_token)
        except OAuthError:
            raise
        except Exception as exc:
            raise OAuthError(
                f"Instagram OAuth authentication failed for account {account_id}: {exc}"
            ) from exc

        now = datetime.now(timezone.utc)
        return InstagramCredential(
            account_id=account_id, access_token=access_token,
            obtained_at=now, expires_at=now + timedelta(seconds=expires_in),
        )

    def refresh(self, credential: InstagramCredential) -> InstagramCredential:
        try:
            response = requests.get(
                REFRESH_URL,
                params={"grant_type": "ig_refresh_token", "access_token": credential.access_token},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                raise Exception(f"Instagram Refresh 요청 실패 ({response.status_code}): {response.text}")
            payload = response.json()
        except Exception as exc:
            raise OAuthError(
                f"Instagram token refresh failed for account {credential.account_id}: {exc}"
            ) from exc

        now = datetime.now(timezone.utc)
        return InstagramCredential(
            account_id=credential.account_id,
            access_token=payload["access_token"],
            obtained_at=now,
            expires_at=now + timedelta(seconds=payload.get("expires_in", 0)),
        )

    def fetch_channel_info(self, credential: InstagramCredential) -> InstagramAccountInfo:
        try:
            response = requests.get(
                ME_URL,
                params={"fields": "id,username", "access_token": credential.access_token},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                raise Exception(f"Instagram 계정 조회 실패 ({response.status_code}): {response.text}")
            payload = response.json()
        except Exception as exc:
            raise OAuthError(
                f"Instagram account info fetch failed for account {credential.account_id}: {exc}"
            ) from exc

        return InstagramAccountInfo(
            account_id=credential.account_id,
            channel_title=payload.get("username", ""),
            ig_user_id=payload.get("id", ""),
        )

    def _authorize_and_capture_code(self) -> str:
        auth_url = f"{AUTHORIZE_URL}?" + urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": _SCOPES,
            "response_type": "code",
        })

        # Redirect URI 확인 조사 - 화면에 어떤 값이 보이든, 실제로 Meta에
        # 보내는 값이 무엇인지 이 로그 한 줄로 정직하게 남긴다(지어낸
        # 값이 아니라 이 요청에 실제로 실린 문자열 그대로 - client_secret
        # 은 authorize 요청 자체에 포함되지 않아 여기 노출되지 않는다).
        logger.info(
            "Instagram OAuth authorize URL: %s (local callback port=%s)",
            auth_url, self.redirect_port,
        )

        server = HTTPServer(("127.0.0.1", self.redirect_port), _CallbackHandler)
        server.received_code = None
        server.received_error = None
        # Critical Bug Fix - UI Freeze on Instagram OAuth Login. timeout을
        # 설정하지 않으면 socketserver.BaseServer.handle_request()는 실제
        # 연결이 올 때까지 무기한 블로킹한다(기본값 None) - 그러면 아래
        # while 루프의 "time.time() < deadline" 확인이 두 번째 반복에서
        # 다시 평가될 기회조차 없어, callback_timeout_seconds가 사실상
        # 전혀 지켜지지 않는다(실제 소켓으로 재현됨). 짧은 주기로 poll해
        # 매 반복마다 deadline을 다시 확인할 수 있게 한다.
        server.timeout = min(1.0, self.callback_timeout_seconds)

        webbrowser.open(auth_url)

        deadline = time.time() + self.callback_timeout_seconds
        while (
            server.received_code is None
            and server.received_error is None
            and time.time() < deadline
        ):
            server.handle_request()
        server.server_close()

        if server.received_error:
            raise OAuthError(f"Instagram 로그인이 거부되었습니다: {server.received_error}")
        if server.received_code is None:
            raise OAuthError("Instagram 로그인 응답을 받지 못했습니다(시간 초과).")
        return server.received_code

    def _exchange_code_for_short_lived_token(self, code: str) -> str:
        response = requests.post(
            SHORT_LIVED_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "code": code,
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise Exception(f"단기 토큰 교환 실패 ({response.status_code}): {response.text}")
        short_lived_token = response.json()["access_token"]
        logger.info(
            "Instagram short-lived token exchange succeeded: token=%s",
            _mask_token(short_lived_token),
        )
        return short_lived_token

    def _exchange_for_long_lived_token(self, short_lived_token: str):
        response = requests.get(
            LONG_LIVED_EXCHANGE_URL,
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": self.client_secret,
                "access_token": short_lived_token,
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise Exception(f"장기 토큰 교환 실패 ({response.status_code}): {response.text}")
        payload = response.json()
        access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 0)
        logger.info(
            "Instagram long-lived token exchange succeeded: token=%s expires_in=%s",
            _mask_token(access_token), expires_in,
        )
        return access_token, expires_in
