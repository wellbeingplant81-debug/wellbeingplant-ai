"""
Sprint90 - OAuthManager (Porting Phase 3).

OneDrive 저장소의 desktop/application/oauth/oauth_manager.py를 옮긴
것이다. 원본에 PySide6 import가 없어 바뀐 것은 credential_health의
import 경로 하나와, 아래 logout() 추가뿐이다.

Qt에 묶여 있던 것은 oauth_worker.py(QThread) 하나였는데 그것은
"콜러블 하나를 백그라운드에서 돌린다"가 전부라, 이미 있는
studio_jobs가 그대로 대신한다.

원본 설명:
EPIC OAuth Manager + Publishing Operations - OAuthManager.

app.providers.upload.google_oauth_service.GoogleOAuthService/file_token_
store.FileTokenStore/oauth_credential.is_expired/oauth_service.OAuthError
(전부 Epic46, 무수정)만 조립한다 - 새 OAuth 로직을 만들지 않는다.

check_health()는 로컬 Token 파일만 읽는다(Network 호출 없음) - Settings
화면을 열 때마다 불러도 안전하다(desktop.controllers.settings_controller.
SettingsController가 생성 시점에 local_settings만 즉시 읽는 것과 동일한
원칙). verify_now()만 실제로 Google에 확인한다(만료 시 Refresh + 가장
저렴한 실제 호출인 fetch_channel_info로 Scope까지 함께 검증) - "자동
조회 금지"(desktop.controllers.analytics_controller.py와 동일한 이
세션의 관례)와 같은 이유로, 이 메서드는 어떤 Signal/Timer에도 자동
연결하지 않는다.

가장 중요한 안전 요구사항 - verify_now()는 credential_loader.
get_valid_credential()을 그대로 재사용하지 않는다. 그 함수는 저장된
Credential이 아예 없으면 authenticate()(실제 대화형 브라우저 로그인)를
자동으로 트리거하도록 설계돼 있다(Upload 시점에는 올바른 동작) - 하지만
"상태만 확인"하는 이 메서드가 그 부작용까지 가져오면 사용자가 예상하지
못한 순간에 브라우저가 열릴 수 있다. 그래서 만료 시의 refresh() 호출만
credential_loader와 동일한 방식(is_expired() 재사용)으로 재현하고,
authenticate()는 reauthenticate()(사용자가 명시적으로 로그인 버튼을
눌렀을 때만)에서만 부른다.
"""

import time

from app.providers.upload.oauth_credential import is_expired
from app.providers.upload.oauth_service import OAuthError
from app.services.oauth_health import (
    CredentialHealth,
    READY,
    EXPIRED,
    REAUTH_REQUIRED,
    UNKNOWN,
    classify_error_message,
)

_DEFAULT_ACCOUNT_ID = "default"


class OAuthManager:

    def __init__(self, oauth_service, token_store, account_id: str = _DEFAULT_ACCOUNT_ID):
        self.oauth_service = oauth_service
        self.token_store = token_store
        self.account_id = account_id

    def check_health(self) -> CredentialHealth:
        try:
            credential = self.token_store.load(self.account_id)
        except Exception as exc:
            return self._unknown(str(exc))

        if credential is None:
            return CredentialHealth(
                REAUTH_REQUIRED, "저장된 Google 로그인이 없습니다.", time.time(),
            )
        if is_expired(credential):
            return CredentialHealth(
                EXPIRED, "Access Token이 만료되었습니다(자동 갱신 필요).", time.time(),
            )
        return CredentialHealth(READY, "정상 연결됨.", time.time())

    def verify_now(self) -> CredentialHealth:
        try:
            credential = self.token_store.load(self.account_id)
        except Exception as exc:
            return self._unknown(str(exc))

        if credential is None:
            return CredentialHealth(
                REAUTH_REQUIRED, "저장된 Google 로그인이 없습니다.", time.time(),
            )

        try:
            if is_expired(credential):
                credential = self.oauth_service.refresh(credential)
                self.token_store.save(credential)
            channel = self.oauth_service.fetch_channel_info(credential)
        except OAuthError as exc:
            return CredentialHealth(classify_error_message(str(exc)), str(exc), time.time())
        except Exception as exc:
            return self._unknown(str(exc))

        return CredentialHealth(
            READY, f"{channel.channel_title} 채널에 연결됨.", time.time(),
        )

    def reauthenticate(self) -> CredentialHealth:
        try:
            credential = self.oauth_service.authenticate(self.account_id)
            self.token_store.save(credential)
        except OAuthError as exc:
            return self._unknown(str(exc))
        return CredentialHealth(READY, "로그인이 완료되었습니다.", time.time())

    def logout(self) -> CredentialHealth:
        """
        Sprint90 추가 - 저장된 로그인을 지운다.

        원본 OAuthManager에는 없지만 FileTokenStore.delete()가 이미 있고
        RealYouTubeRuntime.revoke()가 그것을 쓴다. 새 로직이 아니라 이미
        있는 것을 엮는다.

        Google에 폐기 요청을 보내지 않는다 - 로컬 로그아웃이다. 원격
        폐기는 사용자가 Google 계정 설정에서 하는 것이고, 여기서 임의로
        네트워크를 치면 "로그아웃"이 실패할 수 있는 동작이 된다.
        """

        try:
            self.token_store.delete(self.account_id)
        except Exception as exc:
            return self._unknown(str(exc))

        return CredentialHealth(
            REAUTH_REQUIRED, "로그아웃되었습니다.", time.time(),
        )

    def evaluate_failure_message(self, message: str) -> CredentialHealth:
        return CredentialHealth(classify_error_message(message), message or "", time.time())

    def _unknown(self, message: str) -> CredentialHealth:
        return CredentialHealth(UNKNOWN, message, time.time())


def build_default_oauth_manager() -> OAuthManager:
    # desktop.application.publishing.connectors.youtube_connector.py가
    # 이미 쓰는 것과 동일한 환경 변수/기본 경로 관례.
    #
    # Sprint217 - 기본 경로를 credential_paths에게 맡긴다. 예전에는
    # 상대 경로 "credentials/client_secret.json"이 기본값이었고, 묶은
    # 프로그램은 사람이 두 번 누른 자리(바탕화면)에서 켜지므로 그 파일을
    # 영원히 찾지 못했다 - [Google 로그인]을 눌러도 브라우저가 열리지
    # 않은 실제 원인이다. 환경 변수는 그대로 이긴다.
    import os

    from app.providers.upload.file_token_store import FileTokenStore
    from app.providers.upload.google_oauth_service import GoogleOAuthService
    from app.services import credential_paths

    client_secret_path = credential_paths.resolve(
        "YOUTUBE_OAUTH_CLIENT_SECRET_PATH", "client_secret.json",
    )
    token_store_path = credential_paths.resolve(
        "YOUTUBE_OAUTH_TOKEN_STORE_PATH", "youtube_oauth_tokens.json",
    )
    account_id = os.environ.get("YOUTUBE_OAUTH_ACCOUNT_ID", _DEFAULT_ACCOUNT_ID)

    return OAuthManager(
        oauth_service=GoogleOAuthService(client_secret_path=client_secret_path),
        token_store=FileTokenStore(storage_path=token_store_path),
        account_id=account_id,
    )
