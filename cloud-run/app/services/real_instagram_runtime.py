"""
Sprint97 - Instagram Runtime 이식 (Epic 50, Phase 1).

OneDrive 저장소의 desktop/application/publishing/real_instagram_runtime.py를
가져왔다. 바꾼 것은 import 경로뿐이다 - desktop 계층을 통째로
가져오지 않으므로 Sprint91이 옮겨 둔 app/services 아래를 가리킨다.
실제 Graph API 호출/오류 분류/타임아웃은 한 글자도 바꾸지 않았다 -
Meta가 실제로 돌려주는 오류 코드(190/10/200/210/4/17/32/613)에서
나온 값이라 다시 쓰면 추측이 된다.

아래는 원본 설명이다.

EPIC Instagram Production Ready - RealInstagramRuntime.

desktop.application.publishing.connectors.instagram_adapter.py 안에
있던 실제 Graph API/OAuth 호출 코드를 그대로 옮겨온 것이다(URL/payload/
오류 메시지 전부 무수정) - InstagramRuntimeProtocol이라는 계약 하나로
정리해서 MockInstagramRuntime과 완전히 교체 가능하게 만드는 것이 유일한
목적이다. 새 OAuth 로직/새 Graph API 호출을 만들지 않는다 - 기존
app.providers.upload.credential_loader.get_valid_credential()/
InstagramOAuthService(둘 다 무수정)를 그대로 재사용한다.

"Meta Developer 등록이 끝나는 즉시 App ID/Secret만 입력하면 Instagram
게시가 바로 동작한다" - 그래서 App ID/Secret이 비어 있어도(지금 이
프로젝트의 실제 상태) 생성자는 항상 성공한다. 다만 실제 Meta API를
부르는 5개 메서드(login/refresh_token/upload_media/publish_media/
get_publish_status)는 Network를 시도하기 전에 정직하게 실패한다(추측
성공 없음). revoke()만은 예외다 - 로컬 토큰 삭제일 뿐이라 App ID/Secret
없이도 항상 동작한다.
"""

import requests

from app.providers.upload.credential_loader import get_valid_credential
from app.providers.upload.instagram_credential import InstagramCredential
from app.providers.upload.instagram_oauth_service import InstagramOAuthService
from app.providers.upload.instagram_token_store import InstagramTokenStore
from app.services.instagram_runtime import InstagramRuntimeProtocol
from app.services.publishing_runtime_protocol import TransientRuntimeError

_GRAPH_BASE = "https://graph.instagram.com"
_MEDIA_TYPE = "REELS"
_REQUEST_TIMEOUT_SECONDS = 30

_DEFAULT_REDIRECT_URI = "http://localhost:8551/callback"
_DEFAULT_TOKEN_STORE_PATH = "credentials/instagram_oauth_tokens.json"

_NOT_CONFIGURED_MESSAGE = (
    "Meta App Client ID/Secret이 아직 설정되지 않았습니다 - Setup Wizard "
    "Step 4에서 Instagram Meta App 정보를 입력해주세요(실제 Network 호출 없음)."
)

# EPIC Instagram Upload Production Hardening, Item 4 - 실제 Meta Graph
# API 오류 코드(공식 문서 기준)로 분류한다("추측 금지" - 지어낸 코드가
# 아니라 Meta가 실제로 쓰는 코드다). 190=OAuthException(토큰 만료/무효),
# 10/200/210=권한 부족, 4/17/32/613=Rate Limit 계열.
_TOKEN_EXPIRED_ERROR_CODES = {190}
_PERMISSION_ERROR_CODES = {10, 200, 210}
_RATE_LIMIT_ERROR_CODES = {4, 17, 32, 613}
# Phase 5, Epic (Priority 3) - 사용자 지시대로 "HTTP 500~599"를 그대로
# 범위로 처리한다(이전엔 {500,502,503,504}만 - 501/505~599가 빠져
# 있었다). RATE_LIMIT(429)은 별도로 분류된다(4xx 중 유일한 자동 재시도
# 허용 대상).
_TRANSIENT_HTTP_STATUS_RANGE = range(500, 600)


class InstagramAPIError(Exception):
    """EPIC Instagram Upload Production Hardening, Item 4 - Token Expired/
    Permission/Rate Limit/Unknown(Network 제외 - 그건 TransientRuntimeError
    가 담당)을 나른다. NonRetryableRuntimeError로 만들지 않는다 - 이
    실패들은 사람이 원인을 고친 뒤 기존 retry_plan()으로 수동 재시도할
    수 있어야 한다(retryable=True 그대로 유지, 자동 재시도만 없을 뿐)."""

    def __init__(
        self, message: str, error_category: str = "UNKNOWN_ERROR",
        request_id: str = "", error_body=None, retry_after_seconds: float = None,
    ):
        super().__init__(message)
        self.error_category = error_category
        # EPIC Instagram Upload Production Hardening, Item 6 - 실제 API
        # Request ID(Meta의 fbtrace_id, 지어낸 값 아님)/원본 오류 JSON.
        self.request_id = request_id
        self.error_body = error_body
        # Phase 5, Epic (Priority 3) - RATE_LIMIT(429)일 때만 실제로 값이
        # 있을 수 있다(그 외에는 None).
        self.retry_after_seconds = retry_after_seconds


def _parse_error_body(response):
    try:
        error_body = response.json()
    except ValueError:
        return None
    return error_body if isinstance(error_body, dict) else None


def _parse_retry_after_seconds(response):
    # Phase 5, Epic (Priority 3) - "HTTP 429(Retry-After 준수)". Meta
    # Graph API는 초 단위 정수를 쓴다(HTTP 날짜 형식은 다루지 않는다 -
    # 실제로 관측된 적 없는 값까지 추측해서 처리하지 않는다). 헤더가
    # 없거나 숫자가 아니면 None을 돌려주고, 호출부는 그러면 우리
    # Exponential Backoff만 쓴다.
    headers = getattr(response, "headers", None)
    value = headers.get("Retry-After") if headers else None
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_response_error(error_body, status_code: int) -> str:
    meta_error = error_body.get("error", {}) if isinstance(error_body, dict) else {}
    code = meta_error.get("code") if isinstance(meta_error, dict) else None

    if code in _TOKEN_EXPIRED_ERROR_CODES:
        return "TOKEN_EXPIRED"
    if code in _PERMISSION_ERROR_CODES:
        return "PERMISSION_ERROR"
    if code in _RATE_LIMIT_ERROR_CODES or status_code == 429:
        return "RATE_LIMIT"
    if status_code in _TRANSIENT_HTTP_STATUS_RANGE:
        return "NETWORK_ERROR"
    return "UNKNOWN_ERROR"


def _raise_for_response(response, message: str) -> None:
    error_body = _parse_error_body(response)
    category = _classify_response_error(error_body, response.status_code)
    meta_error = error_body.get("error", {}) if isinstance(error_body, dict) else {}
    request_id = meta_error.get("fbtrace_id", "") if isinstance(meta_error, dict) else ""
    retry_after_seconds = (
        _parse_retry_after_seconds(response) if category == "RATE_LIMIT" else None
    )

    if category == "NETWORK_ERROR":
        raise TransientRuntimeError(
            message, error_category=category, request_id=request_id, error_body=error_body,
        )
    raise InstagramAPIError(
        message, error_category=category, request_id=request_id, error_body=error_body,
        retry_after_seconds=retry_after_seconds,
    )


def _request_or_raise_transient(request_fn, *args, **kwargs):
    try:
        return request_fn(*args, **kwargs)
    except requests.exceptions.RequestException as exc:
        raise TransientRuntimeError(
            f"Instagram 요청 실패(네트워크 오류): {exc}", error_category="NETWORK_ERROR",
        ) from exc


class RealInstagramRuntime(InstagramRuntimeProtocol):

    def __init__(
        self, client_id: str = "", client_secret: str = "",
        redirect_uri: str = _DEFAULT_REDIRECT_URI,
        token_store=None, oauth_service_factory=None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._token_store = token_store or InstagramTokenStore(
            storage_path=_DEFAULT_TOKEN_STORE_PATH,
        )
        self._oauth_service_factory = oauth_service_factory or InstagramOAuthService

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def _ensure_configured(self) -> None:
        if not self.is_configured():
            raise Exception(_NOT_CONFIGURED_MESSAGE)

    def _build_oauth_service(self):
        return self._oauth_service_factory(
            client_id=self._client_id, client_secret=self._client_secret,
            redirect_uri=self._redirect_uri,
        )

    def login(self, account_id: str) -> InstagramCredential:
        self._ensure_configured()
        oauth_service = self._build_oauth_service()
        credential = get_valid_credential(oauth_service, self._token_store, account_id)
        info = oauth_service.fetch_channel_info(credential)
        credential.ig_user_id = info.ig_user_id
        return credential

    def refresh_token(self, credential: InstagramCredential) -> InstagramCredential:
        self._ensure_configured()
        oauth_service = self._build_oauth_service()
        refreshed = oauth_service.refresh(credential)
        refreshed.ig_user_id = credential.ig_user_id
        return refreshed

    def upload_media(
        self, credential: InstagramCredential, video_url: str,
        caption: str, cover_url: str = None, plan=None,
    ) -> str:
        self._ensure_configured()
        data = {
            "media_type": _MEDIA_TYPE, "video_url": video_url,
            "caption": caption, "access_token": credential.access_token,
        }
        if cover_url:
            data["cover_url"] = cover_url

        response = _request_or_raise_transient(
            requests.post, f"{_GRAPH_BASE}/{credential.ig_user_id}/media", data=data,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            _raise_for_response(
                response, f"Instagram 컨테이너 생성 실패 ({response.status_code}): {response.text}",
            )
        return response.json()["id"]

    def publish_media(self, credential: InstagramCredential, container_id: str) -> str:
        self._ensure_configured()
        response = _request_or_raise_transient(
            requests.post, f"{_GRAPH_BASE}/{credential.ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": credential.access_token},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            _raise_for_response(
                response, f"Instagram 게시 실패 ({response.status_code}): {response.text}",
            )
        return response.json()["id"]

    def get_publish_status(self, credential: InstagramCredential, container_id: str) -> str:
        self._ensure_configured()
        response = _request_or_raise_transient(
            requests.get, f"{_GRAPH_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": credential.access_token},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            _raise_for_response(
                response,
                f"Instagram 컨테이너 상태 조회 실패 ({response.status_code}): {response.text}",
            )
        return response.json().get("status_code")

    def get_permalink(self, credential: InstagramCredential, media_id: str) -> str:
        self._ensure_configured()
        response = _request_or_raise_transient(
            requests.get, f"{_GRAPH_BASE}/{media_id}",
            params={"fields": "permalink", "access_token": credential.access_token},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            _raise_for_response(
                response,
                f"Instagram Permalink 조회 실패 ({response.status_code}): {response.text}",
            )
        return response.json().get("permalink", "")

    def revoke(self, credential: InstagramCredential) -> None:
        # Meta에 원격으로 이 로그인을 무효화하는 별도 API는 없다(추측
        # 금지) - 로컬 저장소에서 지우는 것이 이 프로젝트가 보장할 수
        # 있는 전부다. App ID/Secret 없이도 항상 동작한다(Network 없음).
        self._token_store.delete(credential.account_id)
