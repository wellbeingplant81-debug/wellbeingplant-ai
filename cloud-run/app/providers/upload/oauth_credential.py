"""
Epic 46 Sprint 002 - OAuth & Channel Foundation.

OAuth 인증 결과로 저장 가능한 값만 담는다 - Access Token/Refresh
Token뿐이다. Google 계정 비밀번호는 절대 저장하지 않는다(모델에
password류 필드 자체가 없다). account_id를 필수로 가져 여러 계정을
독립적으로 다룰 수 있는 구조를 처음부터 고려한다 - 다만 이번 Sprint는
단일 계정 정상 동작만 목표로 한다(멀티 계정 UI/선택/관리는 범위 밖).
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class OAuthCredential:
    account_id: str
    access_token: str
    refresh_token: str
    expires_at: datetime


def is_expired(credential: OAuthCredential) -> bool:
    return credential.expires_at <= datetime.now(timezone.utc)
