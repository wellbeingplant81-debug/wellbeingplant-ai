"""
Epic 46 Sprint 002 - OAuth & Channel Foundation.

OAuthCredential을 account_id로 저장/조회하는 순수 계층 - 메모리
내(In-Memory) 저장이다. 실제 영속화 방식(암호화 파일/Secret Manager
등)은 보안 요구사항을 신중히 검토해야 하는 별도 결정이라 이번
Foundation Sprint의 범위 밖으로 명시적으로 남겨둔다(YAGNI) - 여러
계정을 독립적으로 저장/조회할 수 있는 구조(account_id 기반 keying)만
지금 확정한다.
"""

from app.providers.upload.oauth_credential import OAuthCredential


class TokenStore:

    def __init__(self):
        self._credentials: dict[str, OAuthCredential] = {}

    def save(self, credential: OAuthCredential) -> None:
        self._credentials[credential.account_id] = credential

    def load(self, account_id: str) -> OAuthCredential | None:
        return self._credentials.get(account_id)
