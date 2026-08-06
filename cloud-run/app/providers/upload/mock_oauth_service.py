"""
Epic 46 Sprint 002 - OAuth & Channel Foundation.

OAuthService의 Mock 구현. 실제 네트워크 호출 없이 결정적으로 성공/
실패 응답을 반환한다 - app/providers/upload/mock_upload_provider.py의
should_fail 스타일을 그대로 따르되, authenticate/refresh/fetch_
channel_info 세 메서드를 독립적으로 실패시킬 수 있도록 플래그를
각각 둔다(세 가지 실패 테스트 케이스를 독립적으로 검증하기 위해).
"""

from datetime import datetime, timedelta, timezone

from app.providers.upload.channel_info import ChannelInfo
from app.providers.upload.oauth_credential import OAuthCredential
from app.providers.upload.oauth_service import OAuthError, OAuthService

_MOCK_TOKEN_LIFETIME = timedelta(hours=1)


class MockOAuthService(OAuthService):

    def __init__(
        self,
        should_fail_auth: bool = False,
        should_fail_refresh: bool = False,
        should_fail_channel: bool = False,
    ):
        self.should_fail_auth = should_fail_auth
        self.should_fail_refresh = should_fail_refresh
        self.should_fail_channel = should_fail_channel

    def authenticate(self, account_id: str) -> OAuthCredential:
        if self.should_fail_auth:
            raise OAuthError(
                f"Mock OAuth authentication failed for account: {account_id}"
            )

        return OAuthCredential(
            account_id=account_id,
            access_token=f"mock_access_{account_id}_1",
            refresh_token=f"mock_refresh_{account_id}",
            expires_at=datetime.now(timezone.utc) + _MOCK_TOKEN_LIFETIME,
        )

    def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        if self.should_fail_refresh:
            raise OAuthError(
                f"Mock token refresh failed for account: {credential.account_id}"
            )

        return OAuthCredential(
            account_id=credential.account_id,
            access_token=f"{credential.access_token}_refreshed",
            refresh_token=credential.refresh_token,
            expires_at=datetime.now(timezone.utc) + _MOCK_TOKEN_LIFETIME,
        )

    def fetch_channel_info(self, credential: OAuthCredential) -> ChannelInfo:
        if self.should_fail_channel:
            raise OAuthError(
                f"Mock channel info fetch failed for account: {credential.account_id}"
            )

        return ChannelInfo(
            account_id=credential.account_id,
            channel_id=f"mock_channel_{credential.account_id}",
            channel_title=f"Mock Channel ({credential.account_id})",
        )
