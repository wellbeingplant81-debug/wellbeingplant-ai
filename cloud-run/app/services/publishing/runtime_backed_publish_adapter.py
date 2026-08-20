"""
EPIC Multi Platform Publishing Runtime, Part 2 - RuntimeBackedPublishAdapter.

Instagram/YouTube/TikTok/Threads가 각자 따로 구현했던(또는 구현했을)
오케스트레이션(Dry Run 분기/Pipeline Trace 기록/실패 분류/Capability
위임)을 한 곳에만 둔다("Platform별 특수처리 제거") - 각 Adapter는
PublishingRuntimeProtocol 구현체(Runtime) + RuntimeCapabilities 선언만
다르고, 이 오케스트레이션 코드는 완전히 동일하다.

EPIC Instagram Production Ready/EPIC Publishing Pipeline Production
Validation이 InstagramAdapter.submit()에 만든 로직을 그대로
일반화했다 - 동작 자체는 바뀌지 않는다(Regression Zero, InstagramAdapter
는 이제 이 클래스의 얇은 서브클래스가 된다).

capabilities.requires_public_url로 "공개 URL이 필요한가(Instagram
Graph API류)" 대 "로컬 파일 경로면 되는가(YouTube 리샘블 업로드류)"를
분기하고, capabilities.two_phase_publish로 "Container 생성 후 별도
Publish 호출이 필요한가" 대 "upload_media() 자체가 이미 최종 게시인가"
를 분기한다 - 이 두 개의 명시적 분기만이 유일하게 허용된 "Platform별
차이"고, 나머지 오케스트레이션 순서(Trace 기록 지점 등)는 완전히
공유된다.
"""

import os
import time

from app.services.studio_service import MEDIA_KINDS
from app.services.publishing.connector_result import ConnectorResult
from app.services.publishing.publish_platform import PublishPlatform
from app.services.publishing_runtime_protocol import (
    NonRetryableRuntimeError,
    TransientRuntimeError,
)

_MAX_CAPTION_LENGTH = 2200  # Instagram Graph API 실제 제한 - 다른 Runtime은 caption을 그냥 무시한다.
_MAX_HASHTAGS = 30

_NO_ASSET_PUBLISHER_MESSAGE = (
    "공개 호스팅이 구성되지 않았습니다(AssetPublisher 미주입) - "
    "{platform} 업로드는 공개 접근 가능한 URL이 필요합니다."
)
# Sprint249-A - 닿을 수 없는 주소는 넘기지 않는다.
#
# Meta 는 우리가 준 주소를 **자기 서버에서 cURL** 한다("we cURL media
# used in publishing attempts"). 그래서 우리 PC 에서만 열리는 주소는
# 아무 소용이 없다 - 그런데 예전 검사는 비어 있는지만 보았고, 저장소를
# http://localhost:9000 으로 잘못 잡아 둔 사람은 그 주소가 그대로 나간
# 뒤 왜 실패했는지 알 수 없었다.
#
# 여기서 막는 것은 "우리가 미리 알 수 있는 것" 뿐이다. 진짜로 열리는지는
# 불러 봐야 알고, 그것은 Meta 가 한다.
_UNREACHABLE_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]")

_NOT_PUBLIC_MESSAGE = (
    "공개 URL 이 아닙니다: {url} - {why}. {platform} 은(는) 그 주소를 "
    "자기 서버에서 직접 열어 보므로, 바깥에서 닿는 https 주소여야 "
    "합니다. 저장소의 공개 주소 설정을 확인해 주십시오."
)


def _why_unreachable(url: str):
    """
    바깥에서 닿을 수 없는 이유. 닿을 수 있어 보이면 None.

    저장소가 어디인지는 보지 않는다 - S3 든 무엇이든 이 계층이 아는
    것은 주소 하나뿐이다.
    """

    from urllib.parse import urlparse

    text = str(url or "").strip()

    if not text:
        return "주소가 비어 있습니다"

    parsed = urlparse(text)

    if parsed.scheme in ("file", ""):
        return "파일 경로입니다"

    # 윈도우 경로는 C: 가 scheme 으로 읽힌다.
    if len(parsed.scheme) == 1:
        return "파일 경로입니다"

    if parsed.scheme != "https":
        return f"{parsed.scheme} 는 공개 주소가 아닙니다"

    host = (parsed.hostname or "").lower()

    if not host:
        return "주소에 서버가 없습니다"

    if host in _UNREACHABLE_HOSTS:
        return "이 PC 안에서만 열리는 주소입니다"

    if _is_private(host):
        return "집·회사 안에서만 열리는 주소입니다"

    return None


def _is_private(host: str) -> bool:
    """사설망 주소인가. 이름이면 아니다 - 우리가 풀어 볼 일이 아니다."""

    import ipaddress

    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


_NO_PUBLIC_URL_MESSAGE = (
    "공개 URL이 없습니다 - 구성된 StorageProvider가 로컬 파일만 참조할 "
    "뿐 공개 URL을 만들지 않습니다. {platform} 업로드는 공개 접근 "
    "가능한 video_url이 필요합니다."
)
_DRY_RUN_MESSAGE = (
    "Dry Run: Storage 업로드/Container 생성/처리 완료까지 실제로 "
    "확인했습니다 - 마지막 API Call(실제 게시)만 Skip 했습니다."
)


# Sprint100 - 원본은 render_profile로 shorts/longform 두 이름을 차례로
# 찾아봤다. 이 저장소의 엔진은 longform을 만들지 않으므로(Sprint91에서
# render_profile을 안 가져오기로 한 그 사실) 찾을 이름이 하나뿐이다.
#
# 이름은 studio_service의 MEDIA_KINDS에서 읽는다 - 이 저장소가 산출물
# 이름을 적어 둔 유일한 자리이고, Sprint93의 메타데이터 계층도 같은
# 곳을 본다. 엔진이 이름을 바꾸면 게시 경로도 같이 따라간다.


def resolve_video_path(output_folder: str) -> str:
    if not output_folder:
        return ""
    return os.path.join(output_folder, *MEDIA_KINDS["video"].split("/"))


def resolve_thumbnail_path(output_folder: str):
    if not output_folder:
        return None

    candidate = os.path.join(output_folder, *MEDIA_KINDS["thumbnail"].split("/"))

    return candidate if os.path.exists(candidate) else None


def build_caption(plan) -> str:
    base = plan.description or plan.title or ""
    hashtags = [f"#{tag.lstrip('#')}" for tag in (plan.hashtags or [])][:_MAX_HASHTAGS]

    if hashtags:
        caption = f"{base}\n\n{' '.join(hashtags)}" if base else " ".join(hashtags)
    else:
        caption = base

    return caption[:_MAX_CAPTION_LENGTH]


def _record_trace(plan, step: str) -> None:
    status = "failed" if step == "failed" else "success"
    plan.pipeline_trace.append({"step": step, "status": status, "timestamp": time.time()})


def _refuse_unreachable(platform: str, url: str):
    """닿을 수 없으면 거절을 만들고, 닿을 수 있으면 None."""

    why = _why_unreachable(url)

    if why is None:
        return None

    # 설정을 고치기 전에는 몇 번을 눌러도 같은 자리에서 같은 이유로
    # 멈춘다 - 재시도 줄에 걸어 두지 않는다.
    return ConnectorResult(
        status="Failed", platform=platform, retryable=False,
        error_category="INVALID_REQUEST",
        message=_NOT_PUBLIC_MESSAGE.format(
            url=url, why=why, platform=platform),
    )


def _default_account_id(platform: str) -> str:
    return os.environ.get(f"{platform.upper()}_OAUTH_ACCOUNT_ID", "default")


class RuntimeBackedPublishAdapter(PublishPlatform):

    def __init__(
        self, platform: str, runtime, asset_publisher=None,
        poll_interval_seconds: float = 3, poll_timeout_seconds: float = 300,
        max_transient_retry_attempts: int = 3, initial_backoff_seconds: float = 2,
    ):
        self.platform = platform
        self._runtime = runtime
        self.asset_publisher = asset_publisher
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self.max_transient_retry_attempts = max_transient_retry_attempts
        self.initial_backoff_seconds = initial_backoff_seconds
        self._results: dict = {}

    def _with_transient_retry(self, fn, *args, **kwargs):
        # EPIC Instagram Upload Production Hardening, Item 2 - Transient
        # RuntimeError만 Exponential Backoff로 재시도한다. 그 외 예외는
        # 첫 시도에서 그대로 전파된다(자동 재시도 없음, 기존 동작 유지).
        attempt = 1
        delay = self.initial_backoff_seconds
        while True:
            try:
                return fn(*args, **kwargs)
            except TransientRuntimeError:
                if attempt >= self.max_transient_retry_attempts:
                    raise
                time.sleep(delay)
                delay *= 2
                attempt += 1

    def supports_platform(self, platform: str) -> bool:
        return platform == self.platform

    def supports_schedule(self) -> bool:
        return self._runtime.capabilities.supports_schedule

    def supports_thumbnail(self) -> bool:
        return self._runtime.capabilities.supports_thumbnail

    def supports_playlist(self) -> bool:
        return self._runtime.capabilities.supports_playlist

    def supports_shorts(self) -> bool:
        return self._runtime.capabilities.supports_shorts

    def submit(self, plan) -> ConnectorResult:
        _record_trace(plan, "preparing")
        caps = self._runtime.capabilities

        if caps.requires_public_url:
            if self.asset_publisher is None:
                _record_trace(plan, "failed")
                return ConnectorResult(
                    status="Failed", platform=self.platform,
                    message=_NO_ASSET_PUBLISHER_MESSAGE.format(platform=self.platform),
                    retryable=False,
                )

            video_path = resolve_video_path(plan.output_folder)
            try:
                asset = self.asset_publisher.publish(video_path)
            except FileNotFoundError as exc:
                # Phase 7, Sprint 3 - Retry Queue Root Cause Analysis
                # (Sprint 2)에서 발견한 구조적 공백 수정. 로컬 원본
                # 파일이 없으면 "다시 시도해도 소용없다"는 사실을
                # 즉시 확정한다(Fail Fast) - retryable=True로 남겨
                # Retry Queue에 영구히 걸어 두지 않는다.
                _record_trace(plan, "failed")
                return ConnectorResult(
                    status="Failed", platform=self.platform, message=str(exc),
                    retryable=False, error_category="FILE_NOT_FOUND",
                )
            except Exception as exc:
                _record_trace(plan, "failed")
                return ConnectorResult(
                    status="Failed", platform=self.platform, message=str(exc), retryable=True,
                )

            if not asset.public_url:
                _record_trace(plan, "failed")
                return ConnectorResult(
                    status="Failed", platform=self.platform,
                    message=_NO_PUBLIC_URL_MESSAGE.format(platform=self.platform),
                    retryable=False,
                )

            # Sprint249-A - 있기만 한 것으로는 모자란다. 바깥에서 닿는
            # 주소여야 한다.
            #
            # 이 갈래(requires_public_url) 안에만 둔다. 공개 URL 이
            # 필요 없는 쪽은 여기 들어오지 않으므로 영향이 없다.
            refused = _refuse_unreachable(self.platform, asset.public_url)

            if refused is not None:
                _record_trace(plan, "failed")
                return refused

            source = asset.public_url
            cover_source = self._resolve_cover_via_asset_publisher(plan.output_folder)
        else:
            source = resolve_video_path(plan.output_folder)
            cover_source = resolve_thumbnail_path(plan.output_folder)

        # History/Operations Center Recording Epic - History Entry의
        # storage_url 필드가 필요로 하는 값이다. requires_public_url=False
        # 플랫폼(YouTube류)은 source가 로컬 경로일 뿐 공개 URL이 아니므로
        # 빈 문자열로 남긴다(지어내지 않는다).
        storage_url = source if caps.requires_public_url else ""

        _record_trace(plan, "uploading_storage")

        try:
            credential = self._with_transient_retry(
                self._runtime.login, _default_account_id(self.platform),
            )
            _record_trace(plan, "preparing_platform")

            if not caps.two_phase_publish and plan.dry_run:
                _record_trace(plan, "completed")
                return ConnectorResult(
                    status="DryRunCompleted", platform=self.platform, message=_DRY_RUN_MESSAGE,
                    storage_url=storage_url,
                )

            caption = build_caption(plan)
            external_ref = self._with_transient_retry(
                self._runtime.upload_media, credential, source, caption, cover_source, plan=plan,
            )

            if caps.two_phase_publish:
                self._wait_until_finished(plan, credential, external_ref)

                if plan.dry_run:
                    _record_trace(plan, "publishing")
                    _record_trace(plan, "completed")
                    result = ConnectorResult(
                        status="DryRunCompleted", platform=self.platform,
                        external_id=external_ref, message=_DRY_RUN_MESSAGE,
                        storage_url=storage_url,
                    )
                    self._results[external_ref] = result
                    return result

                _record_trace(plan, "publishing")
                external_id = self._with_transient_retry(
                    self._runtime.publish_media, credential, external_ref,
                )
            else:
                external_id = external_ref
        except NonRetryableRuntimeError as exc:
            _record_trace(plan, "failed")
            return ConnectorResult(
                status="Failed", platform=self.platform, message=str(exc), retryable=False,
                error_category=getattr(exc, "error_category", ""),
                request_id=getattr(exc, "request_id", ""),
                raw_error_body=getattr(exc, "error_body", None),
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            )
        except Exception as exc:
            _record_trace(plan, "failed")
            error_category = getattr(exc, "error_category", "")
            return ConnectorResult(
                status="Failed", platform=self.platform, message=str(exc),
                # Phase 7, Sprint 3 - Retry Queue Root Cause Analysis
                # (Sprint 2)에서 발견한 구조적 공백 수정. 로컬 파일을
                # 직접 읽는 Runtime(YouTube류)이 FILE_NOT_FOUND로 분류한
                # 예외를 던지면(real_youtube_runtime._classify_upload_
                # error() 참고) 여기서도 Fail Fast(retryable=False)로
                # 확정한다 - 다시 시도해도 파일이 다시 생기지 않는다.
                retryable=error_category != "FILE_NOT_FOUND",
                error_category=error_category,
                request_id=getattr(exc, "request_id", ""),
                raw_error_body=getattr(exc, "error_body", None),
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            )

        _record_trace(plan, "completed")
        # History/Operations Center Recording Epic - Instagram Graph API류
        # (capabilities.supports_permalink=True)만 실제 게시된 콘텐츠의
        # 공개 Permalink를 조회할 수 있다. 조회 자체가 실패해도(예: 일시적
        # 네트워크 문제) 이미 성공한 게시 결과를 실패로 뒤집지 않는다 -
        # Permalink는 부가 정보일 뿐이다.
        permalink = ""
        if caps.supports_permalink:
            try:
                permalink = self._runtime.get_permalink(credential, external_id)
            except Exception:
                permalink = ""
        result = ConnectorResult(
            status="Published", platform=self.platform,
            external_id=external_id, published_at=time.time(),
            permalink=permalink, storage_url=storage_url,
        )
        self._results[external_id] = result
        return result

    def cancel(self, external_id: str) -> ConnectorResult:
        previous = self._results.get(external_id)
        result = ConnectorResult(
            status="Failed",
            platform=previous.platform if previous is not None else self.platform,
            external_id=external_id, message="Cancelled", retryable=False,
        )
        self._results[external_id] = result
        return result

    def status(self, external_id: str) -> ConnectorResult:
        return self._results.get(external_id) or ConnectorResult(
            status="Failed", platform=self.platform, external_id=external_id,
            message="Unknown external_id", retryable=False,
        )

    def _resolve_cover_via_asset_publisher(self, output_folder):
        thumbnail_path = resolve_thumbnail_path(output_folder)
        if thumbnail_path is None or self.asset_publisher is None:
            return None
        try:
            cover_asset = self.asset_publisher.publish(thumbnail_path)
        except Exception:
            return None
        return cover_asset.public_url or None

    def _wait_until_finished(self, plan, credential, container_id) -> None:
        # EPIC Instagram Upload Production Hardening, Item 3 - "업로드
        # 중/Processing/Publishing/Completed" 중 Processing 단계. 대기가
        # 시작되는 시점에 한 번 기록한다(폴링 자체는 Instagram Graph API
        # 두 단계 게시의 고유한 구조이지, 이 Batch가 새로 만드는 재시도가
        # 아니다 - _with_transient_retry는 그 안의 개별 네트워크 호출만
        # 감싼다).
        _record_trace(plan, "processing")
        deadline = time.time() + self.poll_timeout_seconds

        while time.time() < deadline:
            status_code = self._with_transient_retry(
                self._runtime.get_publish_status, credential, container_id,
            )
            if status_code == "FINISHED":
                return
            if status_code in ("ERROR", "EXPIRED"):
                raise Exception(f"{self.platform} 컨테이너 처리 실패: status_code={status_code}")

            time.sleep(self.poll_interval_seconds)

        raise Exception(f"{self.platform} 컨테이너 처리 시간 초과")
