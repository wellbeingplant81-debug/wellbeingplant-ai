"""
Sprint235 - TikTok 에 올리는 자리 (Publish Automation, Phase 2).

Sprint217 이 Login Kit 을 붙여 "누구인가" 는 알았다. 올리는 자리가
없었다 - PublishingRuntimeProtocol 구현체가 YouTube · Instagram 둘뿐
이었다. 이것이 세 번째다.

새 계층을 만들지 않는다
-----------------------
같은 프로토콜, 같은 자리(app/services/real_*_runtime.py), 같은
RuntimeBackedPublishAdapter 가 그대로 조립한다. 로그인은 Sprint217 의
TikTokOAuthService 를 그대로 부른다 - 주소도 PKCE 도 여기서 다시 적지
않는다.

TikTok 이 다른 점
-----------------
    YouTube    파일을 올리면 그것이 곧 게시다
    Instagram  공개 URL 로 컨테이너를 만들고, 따로 게시를 부른다
    TikTok     init 로 자리를 받고 그 자리에 파일을 밀어 넣는다.
               따로 "게시" 를 부르는 API 가 **없다** - 처리가 끝나면
               올라가 있다.

그래서 two_phase_publish=True 로 두되 둘째 걸음은 게시가 아니라
**확인**이다. Adapter 는 첫 걸음 뒤에 상태를 지켜보고(_wait_until_
finished), 그 다음 publish_media 를 부른다 - 우리는 거기서 정말
끝났는지만 본다. 없는 호출을 지어내지 않는다.

공개 URL 이 필요 없다
---------------------
Instagram 은 video_url 을 요구해서 클라우드 저장소가 있어야 한다.
TikTok 은 FILE_UPLOAD 를 받으므로 로컬 파일을 그대로 밀어 넣는다 -
데스크톱 프로그램에는 이쪽이 맞고, 저장소 비용이 들지 않는다.

아직 못 하는 것
---------------
TikTok 앱이 없다(TIKTOK_CLIENT_KEY/SECRET 미설정). 그리고 심사를
통과하지 않은 앱은 비공개(SELF_ONLY)로만 올라간다 - 그것이
DEFAULT_PRIVACY 다. 공개로 보내면 TikTok 이 거절하고 사람은 왜인지
모른다. 설정이 없으면 분명히 거절한다 - 조용히 아무 일도 안 하고
성공했다고 말하지 않는다.
"""

import os

import requests

from app.services.publishing_runtime_protocol import (
    NonRetryableRuntimeError, PublishingRuntimeProtocol, RuntimeCapabilities,
    TransientRuntimeError,
)

# 공식 Content Posting API. 지어낸 주소가 아니다.
#
# Sprint248-A - 올리기 전에 그 계정에 먼저 묻는다. 공식 문서가
# "privacy_level 은 이 응답의 privacy_level_options 중 하나여야 한다"
# 고 적는다.
CREATOR_INFO_URL = (
    "https://open.tiktokapis.com/v2/post/publish/creator_info/query/")

INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# 심사 전에는 이것만 된다.
DEFAULT_PRIVACY = "SELF_ONLY"

# Adapter 가 아는 말. 플랫폼 말을 그대로 흘리지 않는다 - 흘리면
# Adapter 가 플랫폼마다 다른 글자를 알아야 한다.
FINISHED = "FINISHED"
IN_PROGRESS = "IN_PROGRESS"
FAILED = "FAILED"

_TIMEOUT = 60

_UNSET = ("TikTok 앱이 아직 없습니다 - TIKTOK_CLIENT_KEY 와 "
          "TIKTOK_CLIENT_SECRET 을 설정한 뒤에 다시 시도하십시오.")

# 다시 눌러도 같은 자리에서 같은 이유로 죽는 것들.
_PERMANENT = {
    "access_token_invalid": "TOKEN_EXPIRED",
    "access_token_expired": "TOKEN_EXPIRED",
    "scope_not_authorized": "PERMISSION_DENIED",
    "scope_permission_missed": "PERMISSION_DENIED",
    "invalid_param": "INVALID_REQUEST",
    "spam_risk_too_many_posts": "RATE_LIMIT",
}


def _permanent(message: str, error_category: str = "UNKNOWN_ERROR",
               request_id: str = "", error_body=None):
    """
    다시 해도 소용없는 실패.

    NonRetryableRuntimeError 는 맨 Exception 이다 - TransientRuntimeError
    와 달리 인자를 받지 않는다. 그 계약을 바꾸면 이미 그것을 던지는
    두 런타임과 그것을 잡는 Adapter 가 함께 움직여야 한다. 그래서
    여기서는 만든 뒤에 붙인다 - Adapter 도 getattr 로 읽는다.
    """

    made = NonRetryableRuntimeError(message)

    made.error_category = error_category
    made.request_id = request_id
    made.error_body = error_body

    return made


def _error_of(response):
    try:
        body = response.json()
    except Exception:
        return {}, "", ""

    found = body.get("error") if isinstance(body, dict) else None

    if not isinstance(found, dict):
        return body if isinstance(body, dict) else {}, "", ""

    return found, str(found.get("code", "")), str(found.get("log_id", ""))


def _raise_for(response, doing: str):
    """
    무엇이 다시 해 볼 만한 실패이고 무엇이 아닌가.

    5xx 와 429 는 같은 요청을 다시 보내면 될 수 있다. 토큰 · 권한 ·
    잘못된 값은 다시 보내도 똑같다 - 그것을 재시도로 돌리면 줄이
    영원히 도는데 아무 일도 일어나지 않는다.
    """

    found, code, log_id = _error_of(response)
    said = str(found.get("message") or response.text or "")[:400]

    message = f"TikTok {doing} 실패 ({response.status_code}): {said}"

    if response.status_code >= 500:
        raise TransientRuntimeError(message, error_category="SERVER_ERROR",
                                    request_id=log_id, error_body=found)

    if response.status_code == 429:
        raise TransientRuntimeError(
            message, error_category="RATE_LIMIT", request_id=log_id,
            error_body=found,
            retry_after_seconds=_retry_after(response))

    raise _permanent(message, _PERMANENT.get(code, "UNKNOWN_ERROR"),
                     log_id, found)


def _retry_after(response):
    try:
        return float(response.headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None


def _ask(fn, *args, **kwargs):
    """그물이 끊긴 것은 우리 잘못이 아니다 - 다시 해 볼 만하다."""

    try:
        return fn(*args, **kwargs)
    except requests.exceptions.RequestException as failed:
        raise TransientRuntimeError(f"TikTok 에 닿지 못했습니다: {failed}",
                                    error_category="NETWORK_ERROR")


def _video_seconds(path: str):
    """
    그 파일이 몇 초인가. 재지 못하면 None - 모른다는 뜻이다.

    모르는 것을 0 으로 두면 "한도 안" 으로 읽혀 그냥 지나간다. 그래서
    모를 때는 재지 않는다.
    """

    # duration_optimizer 가 이미 ffprobe 로 재고 있다. format=duration 은
    # 컨테이너 전체 길이라 소리든 영상이든 같은 답이 나온다 - 여기서
    # 같은 명령을 다시 적으면 두 자리가 갈린다.
    from app.services import duration_optimizer

    try:
        seconds = float(duration_optimizer.get_audio_duration(path))
    except Exception:
        return None

    # 그 함수는 못 잰 것을 0.0 으로 돌려준다. 0 초짜리 영상은 없으므로
    # 그것은 "못 쟀다" 는 뜻이다 - 한도 안이라고 읽지 않는다.
    return seconds if seconds > 0 else None


class RealTikTokRuntime(PublishingRuntimeProtocol):

    capabilities = RuntimeCapabilities(
        two_phase_publish=True, requires_public_url=False,
        supports_schedule=False, supports_thumbnail=False,
        supports_playlist=False, supports_shorts=True,
        # 올린 것의 주소를 TikTok 이 주지 않는다. 모르면 모른다고 한다.
        supports_permalink=False,
    )

    def __init__(self, client_key: str = "", client_secret: str = "",
                 token_store=None):
        self.client_key = str(client_key or "")
        self.client_secret = str(client_secret or "")
        self._token_store = token_store

    # ── 누구인가 ────────────────────────────────────────────────────
    def is_configured(self) -> bool:
        return bool(self.client_key and self.client_secret)

    def _refuse_if_unset(self) -> None:
        if not self.is_configured():
            raise _permanent(_UNSET, "NOT_CONFIGURED")

    def _build_oauth_service(self):
        """Sprint217 것을 그대로 쓴다. 여기서 로그인을 다시 짓지 않는다."""

        from app.providers.upload import tiktok_oauth_service

        return tiktok_oauth_service.TikTokOAuthService(
            client_key=self.client_key, client_secret=self.client_secret)

    def login(self, account_id):
        self._refuse_if_unset()

        return self._build_oauth_service().authenticate(account_id)

    def refresh_token(self, credential):
        self._refuse_if_unset()

        return self._build_oauth_service().refresh(credential)

    def revoke(self, credential) -> None:
        """
        Login Kit 에 취소 자리가 아직 없다. 지어내지 않는다 - 저장된
        것을 지우는 일은 토큰 보관소가 한다.
        """

        return None

    # ── 올린다 ──────────────────────────────────────────────────────
    def _headers(self, credential):
        return {"Authorization": f"Bearer {credential.access_token}",
                "Content-Type": "application/json; charset=UTF-8"}

    def creator_info(self, credential) -> dict:
        """
        그 계정이 지금 무엇을 허용하는가.

        공식 문서가 init 전에 이것을 묻게 되어 있다 - privacy_level 은
        여기 돌아온 privacy_level_options 중 하나여야 한다.

        읽는 것은 둘뿐이다.

            privacy_level_options        어떤 공개 범위가 되는가
            max_video_post_duration_sec  얼마나 긴 것까지 되는가(선택)

        나머지 칸(이름·사진·댓글 허용 여부 등)은 돌아오지만 지금 쓰지
        않는다. 쓰지 않는 것을 모델에 넣으면 쓰는 척이 된다.
        """

        self._refuse_if_unset()

        asked = _ask(requests.post, CREATOR_INFO_URL,
                     headers=self._headers(credential),
                     json={}, timeout=_TIMEOUT)

        if asked.status_code != 200:
            _raise_for(asked, "계정 확인")

        return (asked.json() or {}).get("data") or {}

    def _refuse_unless_allowed(self, credential, path) -> None:
        """
        SELF_ONLY 로 올릴 수 있는 계정인지 본다.

        허용하지 않으면 올리지 않는다. 다른 공개 범위로 바꾸지 않는다 -
        심사 전 앱은 비공개로만 올릴 수 있고, 그것이 안 되는 계정에
        공개로 보내는 것은 사람이 원한 적 없는 일이다.

        모르는 답도 "된다" 로 읽지 않는다. 목록이 없거나 비어 있으면
        거기서 멈춘다.
        """

        given = self.creator_info(credential)

        allowed = given.get("privacy_level_options")

        if not isinstance(allowed, list) or not allowed:
            raise _permanent(
                "TikTok 이 이 계정의 공개 범위를 알려 주지 않아 "
                "올리지 않았습니다. 잠시 뒤에 다시 시도해 주십시오.",
                "INVALID_REQUEST")

        if DEFAULT_PRIVACY not in allowed:
            raise _permanent(
                f"이 계정은 {DEFAULT_PRIVACY}(나만 보기) 로 올릴 수 "
                f"없습니다 - TikTok 이 알려 준 것은 "
                f"{', '.join(str(a) for a in allowed)} 입니다. "
                "심사를 통과하지 않은 앱은 나만 보기로만 올릴 수 "
                "있으므로 여기서 멈춥니다.",
                "PERMISSION_DENIED")

        # 길이는 알려 줄 때만 본다. 없는 사실로 막지 않는다.
        limit = given.get("max_video_post_duration_sec")

        if not isinstance(limit, (int, float)) or limit <= 0:
            return

        seconds = _video_seconds(path)

        if seconds is None:
            return

        if seconds > float(limit):
            raise _permanent(
                f"이 계정은 {int(limit)}초까지 올릴 수 있는데 영상이 "
                f"{seconds:.0f}초입니다. 짧게 만든 뒤 다시 시도해 "
                "주십시오.",
                "INVALID_REQUEST")

    def upload_media(self, credential, video_url, caption,
                     cover_url=None, plan=None):
        """
        init 로 자리를 받고 그 자리에 파일을 밀어 넣는다. 돌려주는
        것은 publish_id 다 - Adapter 가 그것으로 상태를 지켜본다.

        video_url 이라는 이름이지만 여기서는 **로컬 경로**다
        (capabilities.requires_public_url=False). 프로토콜이 두
        플랫폼을 한 이름으로 부르기 때문이고, 그 이름을 우리가 바꾸면
        Adapter 를 고쳐야 한다.
        """

        self._refuse_if_unset()

        path = str(video_url or "")

        if not os.path.isfile(path):
            # 다시 시도해도 파일이 다시 생기지 않는다.
            raise _permanent(f"올릴 파일이 없습니다: {path}",
                             "FILE_NOT_FOUND")

        size = os.path.getsize(path)

        # Sprint248-A - 묻고 나서 올린다. 여기서 막히면 init 은 한 번도
        # 불리지 않는다.
        self._refuse_unless_allowed(credential, path)

        started = _ask(
            requests.post, INIT_URL, headers=self._headers(credential),
            json={
                "post_info": {
                    "title": str(caption or ""),
                    "privacy_level": DEFAULT_PRIVACY,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,
                    "total_chunk_count": 1,
                },
            },
            timeout=_TIMEOUT)

        if started.status_code != 200:
            _raise_for(started, "업로드 시작")

        given = (started.json() or {}).get("data") or {}
        publish_id = str(given.get("publish_id") or "")
        upload_url = str(given.get("upload_url") or "")

        if not publish_id or not upload_url:
            raise _permanent("TikTok 이 올릴 자리를 주지 않았습니다.")

        with open(path, "rb") as f:
            body = f.read()

        sent = _ask(
            requests.put, upload_url, data=body,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
                "Content-Range": f"bytes 0-{size - 1}/{size}",
            },
            timeout=_TIMEOUT)

        if sent.status_code not in (200, 201, 204):
            _raise_for(sent, "파일 올리기")

        return publish_id

    def get_publish_status(self, credential, container_id):
        """
        플랫폼 말을 프로토콜 말로 옮긴다. 모르는 말이 오면 끝났다고
        하지 않는다 - 아직 도는 중으로 본다.
        """

        self._refuse_if_unset()

        asked = _ask(requests.post, STATUS_URL,
                     headers=self._headers(credential),
                     json={"publish_id": str(container_id)},
                     timeout=_TIMEOUT)

        if asked.status_code != 200:
            _raise_for(asked, "상태 확인")

        said = str(((asked.json() or {}).get("data") or {}).get("status") or "")

        if said == "PUBLISH_COMPLETE":
            return FINISHED

        if said in ("FAILED", "PUBLISH_FAILED"):
            return FAILED

        return IN_PROGRESS

    def publish_media(self, credential, container_id):
        """
        TikTok 에는 따로 게시를 부르는 API 가 없다. 둘째 걸음은
        **확인**이다 - 정말 끝났는지 보고, 끝났으면 그 id 를 돌려준다.
        """

        found = self.get_publish_status(credential, container_id)

        if found != FINISHED:
            raise _permanent(
                f"TikTok 이 아직 게시를 끝내지 않았습니다 ({found}).",
                "NOT_FINISHED")

        return container_id

    def get_permalink(self, credential, media_id) -> str:
        return ""


def build_default_tiktok_runtime() -> RealTikTokRuntime:
    """열쇠는 바깥에서 온다. 코드에 적지 않는다."""

    return RealTikTokRuntime(
        client_key=os.environ.get("TIKTOK_CLIENT_KEY", ""),
        client_secret=os.environ.get("TIKTOK_CLIENT_SECRET", ""))
