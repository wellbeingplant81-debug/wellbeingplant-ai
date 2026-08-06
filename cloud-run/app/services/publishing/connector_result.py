"""
AI Factory 3.0, Part 4 - Publishing Result.

Connector.submit()/cancel()/status()가 공통으로 돌려주는 결과 모양이다.
external_id는 실제 플랫폼 ID가 아니라 uuid4()다("실제 External ID는
UUID 사용" - 실제 YouTube/Instagram/TikTok API를 호출하지 않으므로
진짜 플랫폼 ID를 받을 방법이 없다). retryable은 Publishing Queue(Part
5)가 "사용자가 재시도할 수 있는가"를 판단하는 유일한 근거다 - 이 값이
False인 실패는 재시도 버튼을 눌러도 아무 일도 일어나지 않는다.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConnectorResult:

    status: str
    platform: str
    external_id: str = ""
    published_at: Optional[float] = None
    message: str = ""
    retryable: bool = False
    # EPIC Instagram Upload Production Hardening, Item 4 - "" 기본값(대부분
    # 플랫폼/실패 경로는 여전히 아무 값도 채우지 않는다 - 지어낸 분류
    # 없음). Runtime이 실제로 분류를 아는 경우(Instagram Graph API 실제
    # 오류 코드)만 5가지 중 하나로 채워진다: TOKEN_EXPIRED/PERMISSION_ERROR/
    # RATE_LIMIT/NETWORK_ERROR/UNKNOWN_ERROR.
    error_category: str = ""
    # EPIC Instagram Upload Production Hardening, Item 6 - Publish Log
    # 전용(History에는 넣지 않는다 - 원본 오류 JSON은 History의 "간단한
    # 요약"이라는 성격과 맞지 않는다). request_id는 실제 Meta fbtrace_id
    # (지어낸 값 아님), raw_error_body는 원본 Meta 오류 JSON(dict) 그대로.
    request_id: str = ""
    raw_error_body: Optional[dict] = None
    # History/Operations Center Recording Epic - Instagram Graph API처럼
    # 실제로 공개 Permalink/공개 Storage URL을 돌려주는 Runtime이 생겨서
    # 추가했다("published_url은 항상 빈 문자열이다"라는 이전 가정이
    # Instagram에 한해 더 이상 사실이 아니다). 기본값 ""이라 이 필드를
    # 모르는 기존 Runtime/Adapter는 전혀 영향을 받지 않는다.
    permalink: str = ""
    storage_url: str = ""
    # Phase 5, Epic (Priority 3) - HTTP 429 응답의 Retry-After 헤더 값
    # (초). 자동 재시도 스케줄러가 다음 시도 시각을 계산할 때 우리
    # Exponential Backoff보다 우선한다("429 Retry-After 준수").
    retry_after_seconds: Optional[float] = None
