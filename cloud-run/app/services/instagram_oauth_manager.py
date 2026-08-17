"""
Sprint97 - Instagram Runtime 이식 (Epic 50, Phase 1).

OneDrive 저장소의 desktop/application/oauth/instagram_oauth_manager.py를
가져왔다. 바꾼 것은 import 경로뿐이다 - desktop 계층을 통째로
가져오지 않으므로 Sprint91이 옮겨 둔 app/services 아래를 가리킨다.
OAuthManager는 Sprint90이 이미 옮겨 뒀다 - Instagram 전용 로직은
한 줄도 없고 조립만 한다.

아래는 원본 설명이다.

EPIC Instagram Connector (Production) - Instagram OAuthManager 팩토리.

desktop.application.oauth.oauth_manager.OAuthManager(EPIC OAuth Manager,
무수정)를 그대로 재사용한다 - 그 클래스는 이미 oauth_service/token_store
를 duck typing으로만 다루도록 설계돼 있어, Instagram 전용 로직을 단
한 줄도 추가하지 않고 이 파일 하나(조립만)로 재사용할 수 있다.

desktop.application.oauth.oauth_manager.build_default_oauth_manager()
(YouTube 전용)와 동일한 관례 - 환경 변수로 설정 가능하고, credentials/
아래의 합리적 기본값만 준다.
"""

import os

from app.providers.upload.instagram_oauth_service import InstagramOAuthService
from app.providers.upload.instagram_token_store import InstagramTokenStore
from app.services.oauth_manager import OAuthManager

_DEFAULT_REDIRECT_URI = "http://localhost:8551/callback"
_DEFAULT_TOKEN_STORE_PATH = "credentials/instagram_oauth_tokens.json"
_DEFAULT_ACCOUNT_ID = "default"


def build_default_instagram_oauth_manager() -> OAuthManager:
    client_id = os.environ.get("INSTAGRAM_OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("INSTAGRAM_OAUTH_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("INSTAGRAM_OAUTH_REDIRECT_URI", _DEFAULT_REDIRECT_URI)
    # Sprint217 - 기본 경로는 credential_paths가 정한다. 상대 경로를
    # 기본값으로 두면 묶은 프로그램이 그 파일을 영원히 못 찾는다
    # (YouTube 쪽에서 실제로 그렇게 막혀 있었다). 환경 변수는 그대로
    # 이긴다.
    from app.services import credential_paths

    token_store_path = credential_paths.resolve(
        "INSTAGRAM_OAUTH_TOKEN_STORE_PATH", "instagram_oauth_tokens.json",
    )
    account_id = os.environ.get("INSTAGRAM_OAUTH_ACCOUNT_ID", _DEFAULT_ACCOUNT_ID)

    return OAuthManager(
        oauth_service=InstagramOAuthService(
            client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri,
        ),
        token_store=InstagramTokenStore(storage_path=token_store_path),
        account_id=account_id,
    )
