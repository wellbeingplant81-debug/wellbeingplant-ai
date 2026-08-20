"""
Sprint217 - TikTok Login Kit (Epic 61).

GoogleOAuthService · InstagramOAuthService와 같은 자리의 세 번째
구현체다. 같은 OAuthManager가 그대로 조립한다 - authenticate() /
refresh() / fetch_channel_info() 셋만 맞추면 된다.

Google · Instagram과 무엇이 다른가
----------------------------------
    Google      InstalledAppFlow가 loopback·state·코드교환을 다 해 준다
    Instagram   redirect_uri가 정확히 일치해야 한다. state 없음(추가함)
    TikTok      **PKCE가 필수다.** client_key라는 이름을 쓰고,
                응답이 {"data": ...} 로 한 겹 싸여 오지 않는 대신
                error 필드로 실패를 알린다

PKCE를 왜 쓰는가 - client_secret 때문이다
-----------------------------------------
데스크톱 프로그램에 든 client_secret은 비밀이 될 수 없다. exe를 받은
사람은 누구나 꺼낼 수 있다. 그래서 인가 코드만 훔쳐도 토큰을 받을 수
있게 되면 안 된다.

PKCE는 그 구멍을 막는다. authorize에는 code_verifier의 해시
(code_challenge)만 보내고, 토큰을 받을 때 원본 code_verifier를 낸다.
가로챈 사람은 code_verifier를 모르므로 코드를 토큰으로 바꿀 수 없다.
verifier는 요청마다 새로 만들고 메모리에만 둔다.

바깥 설정이 없으면 아무것도 지어내지 않는다
-------------------------------------------
client_key와 client_secret은 TikTok for Developers에서 사람이 앱을
만들고 받아야 하는 값이다. 없으면 authenticate()는 브라우저를 열지
않고 무엇을 설정해야 하는지 말한다 - 가짜 로그인을 흉내내지 않는다.
"""

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import requests

from app.providers.upload.oauth_credential import OAuthCredential
from app.providers.upload.oauth_service import OAuthError
from app.providers.upload import oauth_loopback

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"

# Sprint217 은 "계정 연결" 만 하려고 user.info.basic 하나로 두었다.
# Sprint235 가 올리는 자리를 만들었는데 여기를 넓히지 않아서, 로그인은
# 되고 올릴 때 권한 오류가 나는 상태였다.
#
# 둘 다 필요하다.
#
#     user.info.basic   누구인지 - 화면이 이름과 사진을 쓴다
#     video.publish     프로필에 바로 올린다 (Direct Post)
#
# 초안으로 보내는 video.upload 가 아니다. 그쪽은 사람이 TikTok 앱에서
# 다시 눌러야 끝나므로, 이 프로그램이 하려는 일과 다르다.
#
# 심사를 통과하지 않은 앱은 이 권한이 있어도 비공개로만 올라간다.
# 그것을 우리가 우회할 방법은 없고, 우회하려 해서도 안 된다.
SCOPES = "user.info.basic,video.publish"

_REQUEST_TIMEOUT_SECONDS = 30
_DEFAULT_REDIRECT_URI = "http://127.0.0.1:8562/callback"


class TikTokAccountInfo:
    """OAuthManager와의 duck typing 호환 모양.

    channel_title이라는 이름은 ChannelInfo(YouTube 전용, 무수정)와
    맞춘 것일 뿐이다 - TikTok에 채널 개념이 있다는 뜻이 아니다."""

    def __init__(self, account_id: str, channel_title: str,
                 open_id: str = ""):
        self.account_id = account_id
        self.channel_title = channel_title
        self.open_id = open_id


def new_verifier() -> str:
    """
    PKCE code_verifier. RFC 7636이 정한 43~128자의 unreserved 문자.

    token_urlsafe(64)는 86자를 준다 - 그 범위 안이다.
    """

    return secrets.token_urlsafe(64)


def challenge_for(verifier: str) -> str:
    """
    code_challenge = BASE64URL(SHA256(verifier)), 패딩 없이.

    TikTok은 S256만 받는다(plain 불가).
    """

    digest = hashlib.sha256(verifier.encode("ascii")).digest()

    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class TikTokOAuthService:

    def __init__(self, client_key: str, client_secret: str,
                 redirect_uri: str = _DEFAULT_REDIRECT_URI,
                 callback_timeout_seconds: float =
                 oauth_loopback.DEFAULT_TIMEOUT_SECONDS):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.callback_timeout_seconds = callback_timeout_seconds

    # ── 바깥 설정이 갖춰졌는가 ────────────────────────────────────
    def missing_setup(self) -> list:
        """없는 것들의 이름. 비어 있으면 로그인을 시도할 수 있다."""

        missing = []

        if not self.client_key:
            missing.append("TIKTOK_CLIENT_KEY")
        if not self.client_secret:
            missing.append("TIKTOK_CLIENT_SECRET")

        return missing

    def _refuse_if_unset(self) -> None:
        missing = self.missing_setup()

        if missing:
            raise OAuthError(
                "TikTok 앱 설정이 없어 로그인을 시작할 수 없습니다. "
                f"{' · '.join(missing)} 를 설정하십시오. TikTok for "
                "Developers에서 앱을 만들고 Login Kit을 켠 뒤 Redirect "
                f"URI로 {self.redirect_uri} 를 등록해야 합니다.")

    # ── 로그인 ────────────────────────────────────────────────────
    def authenticate(self, account_id: str) -> OAuthCredential:
        self._refuse_if_unset()

        verifier = new_verifier()
        state = oauth_loopback.new_state()

        auth_url = AUTHORIZE_URL + "?" + urlencode({
            "client_key": self.client_key,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": state,
            "code_challenge": challenge_for(verifier),
            "code_challenge_method": "S256",
        })

        parsed = urlparse(self.redirect_uri)

        code = oauth_loopback.capture_code(
            auth_url,
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 8562,
            expected_state=state,
            timeout_seconds=self.callback_timeout_seconds,
            platform="TikTok",
        )

        payload = self._token_call({
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            # 가로챈 코드로는 여기를 채울 수 없다.
            "code_verifier": verifier,
        }, account_id)

        return self._to_credential(account_id, payload)

    def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        self._refuse_if_unset()

        if not credential.refresh_token:
            raise OAuthError(
                "TikTok refresh token이 없어 갱신할 수 없습니다. "
                "다시 로그인하십시오.")

        payload = self._token_call({
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": credential.refresh_token,
        }, credential.account_id)

        return self._to_credential(credential.account_id, payload,
                                   fallback_refresh=credential.refresh_token)

    def fetch_channel_info(self, credential: OAuthCredential):
        try:
            response = requests.get(
                USER_INFO_URL,
                params={"fields": "open_id,display_name"},
                headers={"Authorization": f"Bearer {credential.access_token}"},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            body = response.json()
        except Exception as exc:
            raise OAuthError(
                f"TikTok 계정 조회에 실패했습니다: {exc}") from exc

        # TikTok v2는 200으로도 error를 담아 보낸다. 상태 코드만 보면
        # 실패를 성공으로 읽는다.
        said = (body.get("error") or {})

        if said.get("code") not in (None, "", "ok"):
            raise OAuthError(
                f"TikTok 계정 조회에 실패했습니다: "
                f"{said.get('message') or said.get('code')}")

        if response.status_code != 200:
            raise OAuthError(
                f"TikTok 계정 조회에 실패했습니다 ({response.status_code}).")

        user = (body.get("data") or {}).get("user") or {}

        return TikTokAccountInfo(
            account_id=credential.account_id,
            channel_title=user.get("display_name", ""),
            open_id=user.get("open_id", ""),
        )

    # ── 토큰 엔드포인트 ───────────────────────────────────────────
    def _token_call(self, form: dict, account_id: str) -> dict:
        try:
            response = requests.post(
                TOKEN_URL, data=form,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cache-Control": "no-cache",
                },
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise OAuthError(
                f"TikTok 토큰 요청 중 네트워크 오류가 났습니다: "
                f"{exc}") from exc

        try:
            payload = response.json()
        except Exception as exc:
            raise OAuthError(
                f"TikTok 토큰 응답을 읽지 못했습니다 "
                f"({response.status_code}).") from exc

        # 실패는 error/error_description로 온다. 메시지에 코드나
        # 토큰을 함께 싣지 않는다.
        if payload.get("error"):
            raise OAuthError(
                f"TikTok 토큰 교환에 실패했습니다: "
                f"{payload.get('error_description') or payload['error']}")

        if response.status_code != 200:
            raise OAuthError(
                f"TikTok 토큰 교환에 실패했습니다 "
                f"({response.status_code}).")

        if not payload.get("access_token"):
            raise OAuthError(
                f"TikTok 응답에 access_token이 없습니다 "
                f"(account {account_id}).")

        return payload

    def _to_credential(self, account_id: str, payload: dict,
                       fallback_refresh: str = "") -> OAuthCredential:
        expires_in = payload.get("expires_in") or 0

        return OAuthCredential(
            account_id=account_id,
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token") or fallback_refresh,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=int(expires_in)),
        )


def build_default_tiktok_oauth_service() -> TikTokOAuthService:
    return TikTokOAuthService(
        client_key=os.environ.get("TIKTOK_CLIENT_KEY", ""),
        client_secret=os.environ.get("TIKTOK_CLIENT_SECRET", ""),
        redirect_uri=os.environ.get(
            "TIKTOK_OAUTH_REDIRECT_URI", _DEFAULT_REDIRECT_URI),
    )
