"""
EPIC Instagram Connector (Production) - Instagram Credential.

app.providers.upload.oauth_credential.OAuthCredential(Google/YouTube
전용, 무수정)과 의도적으로 다른 모양이다 - Instagram 장기 토큰(Long-
Lived Token, 60일)에는 별도 refresh_token이 없다. 같은 토큰을 "발급
후 24시간 이상 지났고 아직 만료 전"일 때만 자체 갱신 API(graph.
instagram.com/refresh_access_token)로 60일 더 연장할 수 있을 뿐이다 -
Google의 "영구 refresh_token" 모델과 근본적으로 다르다. 이 창을
놓치면(만료 후) 복구 불가 - 전체 재로그인만 답이다.

is_expired()는 새로 만들지 않는다 - app.providers.upload.oauth_
credential.is_expired()가 credential.expires_at만 읽으므로(duck
typing) 이 Credential에도 그대로 재사용된다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_MIN_REFRESH_AGE = timedelta(hours=24)


@dataclass
class InstagramCredential:
    account_id: str
    access_token: str
    obtained_at: datetime
    expires_at: datetime
    # EPIC Instagram Production Ready - InstagramRuntimeProtocol.login()
    # 하나가 access_token과 ig_user_id를 함께 돌려줄 수 있게 한다(기존
    # InstagramOAuthService.fetch_channel_info()를 없애지 않는다 - Real
    # Runtime의 login()이 여전히 그 함수로 이 값을 채운다).
    ig_user_id: str = ""


def is_refreshable(credential: InstagramCredential) -> bool:
    from app.providers.upload.oauth_credential import is_expired

    if is_expired(credential):
        return False
    return (datetime.now(timezone.utc) - credential.obtained_at) >= _MIN_REFRESH_AGE
