"""
Epic 46 Sprint 002 - OAuth & Channel Foundation.

OAuth Service -> Credential -> (Channel Information -> UploadProvider는
이후 Sprint 범위) 흐름 중 "Credential을 항상 유효한 상태로 가져온다"는
오케스트레이션만 담당한다. TokenStore에 저장된 Credential이 없으면
새로 인증하고, 있지만 만료됐으면 자동으로 갱신한다 - 매번 새로 인증
하지 않는다("Access Token 자동 갱신").
"""

from typing import Optional, Protocol

from app.providers.upload.oauth_credential import OAuthCredential, is_expired
from app.providers.upload.oauth_service import OAuthService


class CredentialStore(Protocol):
    """
    Epic 46 Sprint 008 - mypy를 위한 순수 타입 힌트용 Protocol이다
    (런타임 동작 무변화). TokenStore(Sprint002, In-Memory)와
    FileTokenStore(Sprint003, 파일 기반)는 둘 다 save/load 시그니처가
    동일해 원래도 Duck Typing으로 호환됐다 - 이 Protocol은 그 사실을
    타입 체커에게도 알려줄 뿐, 두 클래스 중 어느 쪽도 수정하지 않는다.
    """

    def save(self, credential: OAuthCredential) -> None: ...

    def load(self, account_id: str) -> Optional[OAuthCredential]: ...


def get_valid_credential(
    oauth_service: OAuthService, token_store: CredentialStore, account_id: str
):
    credential = token_store.load(account_id)

    if credential is None:
        credential = oauth_service.authenticate(account_id)
        token_store.save(credential)
        return credential

    if is_expired(credential):
        credential = oauth_service.refresh(credential)
        token_store.save(credential)

    return credential
