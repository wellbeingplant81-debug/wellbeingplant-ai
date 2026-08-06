"""
Sprint91 - Upload Runtime 이식 (Porting Phase 4).

OneDrive 저장소에서 무수정으로 가져왔다. 표준 라이브러리(abc,
dataclasses)만 쓰므로 옮기는 데 걸리는 것이 없었다. 아래 설명이
언급하는 Instagram Runtime은 이 저장소에 없다 - 그쪽은 이식
대상이 아니다(Sprint91 금지 항목).

아래는 원본 설명이다.

EPIC Multi Platform Publishing Runtime, Part 1 - PublishingRuntimeProtocol.

EPIC Instagram Production Ready가 만든 InstagramRuntimeProtocol(login/
refresh_token/upload_media/publish_media/get_publish_status/revoke)의
메서드 이름/모양을 그대로 표준으로 승격한 것이다 - "기존 Instagram
Runtime 구조를 표준으로 사용"이라는 지시를 그대로 따른다(이름을 하나도
바꾸지 않는다). desktop.application.publishing.instagram_runtime.
InstagramRuntimeProtocol은 이제 이 클래스를 상속한다(무수정 - Python
ABC는 메서드 시그니처를 엄격히 강제하지 않으므로 RealInstagramRuntime/
MockInstagramRuntime은 손댈 필요가 없다).

video_url/caption/cover_url 파라미터 이름은 그대로 유지하되 의미를
일반화한다 - capabilities.requires_public_url=True인 플랫폼(Instagram
Graph API류)에서는 실제로 "공개 URL"이어야 하고, False인 플랫폼
(YouTube 리샘블 업로드류)에서는 "로컬 파일 경로"를 그대로 담는다.
plan(선택, 기본 None)은 순수 추가 파라미터다 - YouTube처럼 title/
description/hashtags/thumbnail을 구조화된 형태로 그대로 알아야 하는
Runtime을 위한 것이고, Instagram Runtime은 여전히 caption 문자열만
쓰고 이 값을 그냥 무시한다(Regression Zero).

NonRetryableRuntimeError - Runtime이 이 예외를 던지면 RuntimeBackedPublishAdapter
는 retryable=False로 분류한다(예: YouTube Upload가 Settings로 꺼져
있음 - 재시도해도 똑같이 실패할 것이 확실하다). 그 외 모든 예외
(OAuthError 포함)는 기존 InstagramAdapter와 동일하게 retryable=True로
취급한다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class NonRetryableRuntimeError(Exception):
    pass


class TransientRuntimeError(Exception):
    """EPIC Instagram Upload Production Hardening - NonRetryableRuntimeError
    와 정반대 극단이다. Runtime이 이 예외를 던지면 RuntimeBackedPublishAdapter
    가 Exponential Backoff로 자동 재시도한다(네트워크 오류/Meta 5xx류 -
    사람 개입 없이 같은 요청을 다시 보내면 성공할 가능성이 높은 일시적
    실패만 해당). "자동 Retry 금지" 원칙은 Plan/Controller 레벨(수동
    retry_plan())에서 여전히 그대로다 - 이 재시도는 submit() 호출 하나
    안에서 벌어지는 저수준 I/O 재시도일 뿐이고, 재시도를 모두 소진하면
    기존과 동일하게 retryable=True인 Failed 결과로 귀결된다. 그 외 모든
    예외(OAuthError/Token Expired/Permission/Rate Limit 포함)는 무수정
    그대로 - 자동으로 재시도하지 않는다."""

    def __init__(
        self, message: str = "", error_category: str = "NETWORK_ERROR",
        request_id: str = "", error_body=None, retry_after_seconds: float = None,
    ):
        super().__init__(message)
        self.error_category = error_category
        # EPIC Instagram Upload Production Hardening, Item 6 - Publish Log가
        # 실제 API Request ID(Meta의 fbtrace_id)/원본 오류 JSON을 남길 수
        # 있도록 담아 둘 뿐이다(대부분의 호출자는 그냥 기본값 그대로 둔다).
        self.request_id = request_id
        self.error_body = error_body
        # Phase 5, Epic (Priority 3) - HTTP 429의 Retry-After 헤더 값(초).
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class RuntimeCapabilities:
    # 구조적 차이(Adapter가 오케스트레이션 분기에 쓴다).
    two_phase_publish: bool  # True: upload(container)->poll->별도 publish_media 호출 필요(Instagram Graph API류). False: upload_media()가 이미 최종 게시(YouTube류) - publish_media는 호출되지 않는다.
    requires_public_url: bool  # True: video_url이 공개 URL이어야 함(AssetPublisher 필요). False: video_url은 로컬 파일 경로.
    # 플랫폼 자체의 사실(기존 PublishPlatform.supports_* 4종과 동일한 의미) - Adapter가 그대로 위임한다.
    supports_schedule: bool = False
    supports_thumbnail: bool = False
    supports_playlist: bool = False
    supports_shorts: bool = False
    # History/Operations Center Recording Epic - Instagram Graph API류만
    # 게시 후 실제 Permalink를 조회하는 별도 API를 갖고 있다. 기본값
    # False라 기존 RuntimeCapabilities(...) 생성 호출은 전부 무수정으로
    # 그대로 유효하다.
    supports_permalink: bool = False


class PublishingRuntimeProtocol(ABC):

    capabilities: RuntimeCapabilities

    @abstractmethod
    def login(self, account_id):
        raise NotImplementedError

    @abstractmethod
    def refresh_token(self, credential):
        raise NotImplementedError

    @abstractmethod
    def upload_media(self, credential, video_url, caption, cover_url=None, plan=None):
        raise NotImplementedError

    @abstractmethod
    def publish_media(self, credential, container_id):
        raise NotImplementedError

    @abstractmethod
    def get_publish_status(self, credential, container_id):
        raise NotImplementedError

    @abstractmethod
    def revoke(self, credential):
        raise NotImplementedError

    def get_permalink(self, credential, media_id) -> str:
        """게시된 콘텐츠의 실제 공개 URL을 조회한다 - capabilities.
        supports_permalink=True인 Runtime만 의미 있게 재정의한다. 추상
        메서드가 아니다(기본값 "") - YouTube/TikTok/Threads Runtime
        6개를 전부 건드리지 않기 위해서다(Regression Zero, "Platform별
        특수처리"는 여전히 supports_permalink 분기 하나뿐)."""
        return ""
