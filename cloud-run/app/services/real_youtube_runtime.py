"""
Sprint91 - Upload Runtime 이식 (Porting Phase 4).

OneDrive 저장소의 desktop/application/publishing/real_youtube_runtime.py를
가져왔다. 바꾼 것은 PublishingRuntimeProtocol의 import 경로 하나뿐이다
(desktop 계층을 통째로 가져오지 않으므로 app/services 아래로 옮겼다).
분류 규칙과 capabilities는 한 글자도 바꾸지 않았다 - 실제 YouTube Data
API 응답에서 나온 값이라 다시 쓰면 추측이 된다.

아래는 원본 설명이다.

EPIC Multi Platform Publishing Runtime, Part 3 - RealYouTubeRuntime.

기존 desktop.application.publishing.connectors.youtube_connector.
YouTubeConnector(AI Factory 3.1, 무수정으로 그대로 남는다 - Legacy
ConnectorRegistry/자체 테스트 스위트가 계속 참조한다)의 실제 로직을
PublishingRuntimeProtocol 계약 아래로 "그대로" 옮긴 것이다 - 새 YouTube
API 호출 코드를 만들지 않는다. OAuth Credential 체인(app.providers.
upload.credential_loader.get_valid_credential + GoogleOAuthService +
FileTokenStore)과 실제 업로드(app.providers.upload.
youtube_upload_provider.YouTubeUploadProvider)를 그대로 재사용한다.

안전장치(사용자 확인 완료, 2026-07-27) - 이 저장소에는 이미 실제로
발급된 YouTube OAuth Token(credentials/youtube_oauth_tokens.json)이
있다. app.config.ENABLE_YOUTUBE_UPLOAD가 False(기본값)면 login()이
get_valid_credential()을 절대 호출하지 않고, NonRetryableRuntimeError
(DISABLED_MESSAGE)를 즉시 던진다 - RuntimeBackedPublishAdapter가 이를
retryable=False Failed로 변환한다(기존 YouTubeConnector와 동일한
문구/의미).

capabilities.two_phase_publish=False - YouTube Data API의 실제 업로드
(resumable upload)는 그 자체가 이미 최종 게시라 Instagram Graph API류의
별도 Container->Publish 2단계가 없다. capabilities.requires_public_url=
False - YouTubeUploadProvider는 로컬 파일 경로를 직접 읽어 업로드하므로
AssetPublisher(공개 URL)가 필요 없다.

Priority 4(YouTube Shorts Auto Publish), Sprint 1 - error_category
분류 + get_permalink() 추가. YouTubeUploadProvider가 실제 HttpError로
부터 옮겨 담아 둔 UploadResult.error_status_code/error_reason(새 필드,
Regression Zero - 기본값 None이라 기존 호출부는 전혀 영향받지 않는다)
을 그대로 읽어 분류할 뿐, 새 HTTP 호출/새 판정 로직을 만들지 않는다.

QUOTA_EXCEEDED는 의도적으로 Instagram의 RATE_LIMIT과 별개 이름이다 -
YouTube Data API 일일 할당량 소진은 태평양 시간 자정에만 리셋되므로
(초/분 단위로 풀리는 Rate Limit과 근본적으로 다르다), desktop.
application.resilience.auto_retry_policy.AUTO_RETRY_ELIGIBLE_ERROR_
CATEGORIES(NETWORK_ERROR/RATE_LIMIT만 허용)에 절대 포함되면 안 된다 -
이름을 다르게 둠으로써 그 실수를 코드 수준에서 원천 차단한다.

get_permalink()는 실제 API 호출이 필요 없다 - YouTubeUploadProvider._
real_upload()가 이미 만드는 실제 URL 형식(https://youtu.be/{video_id})
을 문자열로만 재구성한다(Instagram의 get_permalink()처럼 별도 GET
요청이 필요 없다 - video_id 자체가 이미 영구적인 공개 URL의 일부다).
"""

import os

from app import config
from app.providers.upload.credential_loader import get_valid_credential
from app.providers.upload.file_token_store import FileTokenStore
from app.providers.upload.google_oauth_service import GoogleOAuthService
from app.providers.upload.youtube_upload_provider import (
    CONNECTION_ERROR_REASON,
    FILE_NOT_FOUND_REASON,
    YouTubeUploadProvider,
)
from app.services.publishing_runtime_protocol import (
    NonRetryableRuntimeError,
    PublishingRuntimeProtocol,
    RuntimeCapabilities,
)

DISABLED_MESSAGE = "YouTube Upload disabled by Settings"


class YouTubeAPIError(Exception):
    """Priority 4 - Instagram의 InstagramAPIError와 동일한 역할이다.
    NonRetryableRuntimeError로 만들지 않는다 - QUOTA_EXCEEDED조차
    "지금 자동으로 다시 시도해도 소용없다"는 뜻이지 "영원히 재시도
    불가능"은 아니다(내일 quota가 리셋되면 사람이 수동으로 다시 시도할
    수 있어야 한다 - retryable=True 그대로 유지, 자동 재시도만 없을
    뿐)."""

    def __init__(self, message: str, error_category: str = "UNKNOWN_ERROR"):
        super().__init__(message)
        self.error_category = error_category


def _classify_upload_error(status_code, reason: str) -> str:
    # Priority 4, Sprint 3 - 실제 "짧은 네트워크 차단" 검증 중 발견된
    # 실제 Gap 수정. 연결 자체가 실패하면(OSError 계층 - DNS 실패/
    # Connection Refused/Timeout) status_code가 없다 - 하지만
    # YouTubeUploadProvider가 이 경우를 CONNECTION_ERROR_REASON
    # sentinel로 이미 표시해 뒀으므로, status_code 없이도 확실하게
    # NETWORK_ERROR로 분류할 수 있다.
    # Phase 7, Sprint 3 - Retry Queue Root Cause Analysis(Sprint 2)에서
    # 발견된 실제 부작용 수정. FILE_NOT_FOUND_REASON을 CONNECTION_ERROR_
    # REASON보다 먼저 확인한다 - 로컬 원본 파일이 없는 것은 네트워크
    # 문제가 아니다(자동 재시도 허용 목록에 절대 포함되면 안 된다).
    if reason == FILE_NOT_FOUND_REASON:
        return "FILE_NOT_FOUND"
    if reason == CONNECTION_ERROR_REASON:
        return "NETWORK_ERROR"
    # isinstance 확인 - error_status_code는 UploadResult의 선택적 필드다
    # (기본값 None). HttpError가 아닌 그 외 일반 예외는 이 값을 채우지
    # 않으므로, 실수로 무언가 다른 타입이 들어와도 조용히 UNKNOWN_ERROR로
    # 떨어져야지 여기서 예외가 나면 안 된다.
    if not isinstance(status_code, int):
        return "UNKNOWN_ERROR"
    if status_code == 401:
        return "TOKEN_EXPIRED"
    if status_code == 403:
        if "quota" in (reason or "").lower():
            return "QUOTA_EXCEEDED"
        return "PERMISSION_ERROR"
    if 500 <= status_code <= 599:
        return "NETWORK_ERROR"
    return "UNKNOWN_ERROR"


# Sprint255 - 자리는 credential_paths 가 정한다.
#
# 예전에는 여기도 상대 경로였다. 업로드 걸음(youtube_upload_step_
# service)과 이 런타임이 각자 같은 글자를 따로 들고 있었고, 둘 다 켠
# 자리를 따라갔다 - 로그인이 쓰는 자리와 갈라진 이유다.
def _default_client_secret_path() -> str:
    from app.services import youtube_upload_step_service

    return youtube_upload_step_service.client_secret_path()


def _default_token_store_path() -> str:
    from app.services import youtube_upload_step_service

    return youtube_upload_step_service.token_store_path()


class RealYouTubeRuntime(PublishingRuntimeProtocol):

    capabilities = RuntimeCapabilities(
        two_phase_publish=False, requires_public_url=False,
        supports_schedule=True, supports_thumbnail=True,
        supports_playlist=True, supports_shorts=True,
        supports_permalink=True,
    )

    def __init__(self, client_secret_path: str = None, token_store=None):
        self._client_secret_path = client_secret_path or _default_client_secret_path()
        self._token_store = token_store or FileTokenStore(
            storage_path=_default_token_store_path()
        )

    def login(self, account_id: str):
        if not config.ENABLE_YOUTUBE_UPLOAD:
            # get_valid_credential()/YouTubeUploadProvider는 이 분기
            # 안에서는 아예 호출되지 않는다 - 위쪽의 import는 클래스
            # 정의일 뿐 실행이 아니다.
            raise NonRetryableRuntimeError(DISABLED_MESSAGE)

        oauth_service = GoogleOAuthService(client_secret_path=self._client_secret_path)
        return get_valid_credential(oauth_service, self._token_store, account_id)

    def refresh_token(self, credential):
        # get_valid_credential()이 이미 만료 여부를 확인해 필요하면
        # 갱신까지 수행한다 - login()과 동일한 체인을 다시 타는 것이
        # 새 로직을 만드는 것보다 안전하다(기존 계약 재사용).
        return self.login(credential.account_id)

    def upload_media(self, credential, video_url, caption, cover_url=None, plan=None):
        provider = YouTubeUploadProvider(credential=credential)
        metadata = self._build_metadata(plan, cover_url)
        upload_result = provider.upload(video_url, metadata)

        if not upload_result.success:
            category = _classify_upload_error(
                upload_result.error_status_code, upload_result.error_reason,
            )
            raise YouTubeAPIError(
                upload_result.error or "YouTube upload failed", error_category=category,
            )

        return upload_result.upload_id or ""

    def publish_media(self, credential, container_id):
        # 단일 단계(capabilities.two_phase_publish=False) - upload_media()
        # 가 이미 최종 게시를 마쳤다. RuntimeBackedPublishAdapter는 이
        # 메서드를 실제로 호출하지 않는다 - ABC 계약을 만족하기 위해서만
        # 존재하는 통과(passthrough)다.
        return container_id

    def get_publish_status(self, credential, container_id):
        # 단일 단계라 폴링 자체가 일어나지 않는다(Adapter가 호출하지
        # 않는다) - 항상 완료 상태로 답한다.
        return "FINISHED"

    def revoke(self, credential) -> None:
        self._token_store.delete(credential.account_id)

    def get_permalink(self, credential, media_id: str) -> str:
        # 실제 API 호출 불필요 - video_id 자체가 이미 영구 공개 URL의
        # 일부다(YouTubeUploadProvider._real_upload()가 업로드 성공
        # 직후 만드는 url=f"https://youtu.be/{video_id}"와 동일한 형식).
        return f"https://youtu.be/{media_id}" if media_id else ""

    @staticmethod
    def _build_metadata(plan, cover_url) -> dict:
        metadata = {
            "title": plan.title if plan is not None else "",
            "description": plan.description if plan is not None else "",
            "hashtags": (plan.hashtags if plan is not None else []) or [],
        }
        if cover_url:
            metadata["thumbnail_path"] = cover_url
        return metadata
