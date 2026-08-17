"""
Epic 46 Sprint 003 - Real Google OAuth Integration.

OAuthService(Sprint002)의 실제 구현체 - Desktop Application Flow
(InstalledAppFlow)로 브라우저 로그인을 수행하고, Refresh Token으로
Access Token을 갱신하며, YouTube Data API로 채널 정보를 조회한다.
MockOAuthService(Sprint002, 무수정)와 나란히 존재하는 두 번째 구현체일
뿐이다 - OAuthService ABC/OAuthError/CredentialLoader/TokenStore는
전혀 바꾸지 않는다.

Google API 관련 코드(InstalledAppFlow/Credentials/build)는 전부 이
파일 안에만 존재한다 - 다른 어떤 파일도 google_auth_oauthlib/
googleapiclient를 직접 import하지 않는다("Google API 관련 코드는
OAuthService 뒤에 숨긴다").

Client Secret은 코드에 하드코딩하지 않는다 - client_secret_path
생성자 인자로 실제 파일 경로를 받는다(설정 분리).

OAuth Scope는 최소 권한만 요청한다 - Sprint003 당시에는 "채널 인식"만이
목표라 읽기 전용 Scope만 썼다.

2026-07-21 - 실제 운영 검증(Epic46 Sprint004+ 업로드 로직은 이미
구현돼 있었으나 Scope가 없어 막혀 있었다)에서 youtube.upload Scope가
필요함을 확인해 추가했다 - youtube.readonly는 채널 조회에 계속
쓰이므로 제거하지 않고 그대로 유지한다. 이 파일 밖의 어떤 로직도
바뀌지 않았다 - 사용자가 새 Scope로 다시 로그인(재동의)해야 한다.
"""

import json
import os
from datetime import timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.providers.upload.channel_info import ChannelInfo
from app.providers.upload.oauth_credential import OAuthCredential
from app.providers.upload.oauth_service import OAuthError, OAuthService

_YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleOAuthService(OAuthService):

    def __init__(self, client_secret_path: str):
        self.client_secret_path = client_secret_path

    def authenticate(self, account_id: str) -> OAuthCredential:
        # Sprint217 - 파일이 없다는 것을 먼저, 사람이 읽을 수 있는 말로
        # 말한다.
        #
        # 예전에는 이 검사가 없어서 from_client_secrets_file()이 던지는
        # FileNotFoundError가 그대로 아래 문장에 실려 나갔다. 화면에
        # 뜬 것은 이것이었다(바탕화면 exe에서 실측).
        #
        #   ⚪ 알 수 없음
        #   Google OAuth authentication failed for account default:
        #   [Errno 2] No such file or directory:
        #   'credentials/client_secret.json'
        #
        # 받은 사람이 이 글로 할 수 있는 일이 없다. 무엇이 없고 어디에
        # 두면 되는지를 적는다 - 경로는 지어내지 않고 실제로 읽으려던
        # 그 자리를 그대로 적는다.
        if not os.path.exists(self.client_secret_path):
            raise OAuthError(
                "Google 로그인에 필요한 자격증명 파일이 없어 브라우저를 "
                "열지 못했습니다. Google Cloud Console에서 만든 "
                "데스크톱 앱 OAuth 클라이언트의 JSON 파일을 이 자리에 "
                f"두십시오: {os.path.abspath(self.client_secret_path)}")

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secret_path,
                scopes=_YOUTUBE_SCOPES,
            )
            google_credentials = flow.run_local_server(port=0)
        except Exception as exc:
            raise OAuthError(
                f"Google OAuth authentication failed for account {account_id}: {exc}"
            ) from exc

        return self._to_oauth_credential(account_id, google_credentials)

    def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        try:
            google_credentials = self._to_google_credentials(credential)
            google_credentials.refresh(Request())
        except Exception as exc:
            raise OAuthError(
                f"Google token refresh failed for account {credential.account_id}: {exc}"
            ) from exc

        return self._to_oauth_credential(credential.account_id, google_credentials)

    def fetch_channel_info(self, credential: OAuthCredential) -> ChannelInfo:
        try:
            google_credentials = self._to_google_credentials(credential)
            youtube = build("youtube", "v3", credentials=google_credentials)
            response = youtube.channels().list(part="snippet", mine=True).execute()
            items = response.get("items") or []

            if not items:
                raise OAuthError(
                    f"No YouTube channel found for account {credential.account_id}"
                )

            channel = items[0]
        except OAuthError:
            raise
        except Exception as exc:
            raise OAuthError(
                f"Channel info fetch failed for account {credential.account_id}: {exc}"
            ) from exc

        return ChannelInfo(
            account_id=credential.account_id,
            channel_id=channel["id"],
            channel_title=channel["snippet"]["title"],
        )

    def _to_google_credentials(self, credential: OAuthCredential) -> Credentials:
        client_config = self._load_client_config()

        return Credentials(
            token=credential.access_token,
            refresh_token=credential.refresh_token,
            token_uri=_TOKEN_URI,
            client_id=client_config["client_id"],
            client_secret=client_config["client_secret"],
            scopes=_YOUTUBE_SCOPES,
        )

    def _load_client_config(self) -> dict:
        with open(self.client_secret_path, encoding="utf-8") as f:
            raw = json.load(f)

        return raw.get("installed") or raw.get("web") or {}

    def _to_oauth_credential(
        self, account_id: str, google_credentials
    ) -> OAuthCredential:
        expiry = google_credentials.expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        return OAuthCredential(
            account_id=account_id,
            access_token=google_credentials.token,
            refresh_token=google_credentials.refresh_token,
            expires_at=expiry,
        )
