"""
Sprint108 - Distribution Upload Provider Foundation.

실제 플랫폼 업로드 전 Provider 추상화 계층. Sprint104의
platform_adapter.PlatformAdapter(distribution 큐 아이템을 받아 발행
상태를 판단하는 상위 계층)와는 다른, 더 낮은 레벨의 추상화다 -
UploadProvider는 큐/발행 판단과 무관하게 "파일 하나를 업로드한다"는
행위 자체만 추상화한다.

이 파일이 하지 않는 것:
- 실제 플랫폼 API 호출
- OAuth / Token 관리
- Scheduler / Queue 연결(distribution_queue.py 소관)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class UploadResult:
    success: bool
    upload_id: Optional[str]
    url: Optional[str]
    error: Optional[str]
    # Epic 46 Sprint 005 - Thumbnail 업로드 실패는 영상 업로드 자체의
    # success를 바꾸지 않는다(영상은 이미 성공). 기본값이 있는 추가
    # 필드라 기존 4개 필드만 넘기던 호출부는 전혀 영향받지 않는다.
    thumbnail_error: Optional[str] = None
    # Epic 46 Sprint 006 - Playlist 추가 실패도 같은 이유로 영상
    # 업로드 자체의 success에는 영향을 주지 않는다.
    playlist_error: Optional[str] = None
    # Priority 4(YouTube Shorts Auto Publish) - 실제 googleapiclient.
    # errors.HttpError의 구조화된 정보(status_code/reason)를 보존한다.
    # RealYouTubeRuntime이 이 값으로 error_category(NETWORK_ERROR/
    # QUOTA_EXCEEDED/TOKEN_EXPIRED/PERMISSION_ERROR)를 계산한다 -
    # error(문자열)만으로는 정확한 분류가 불가능하다(Instagram의
    # _classify_response_error()와 동일한 필요성, HttpError 객체는
    # Provider 경계를 못 넘으므로 여기서 구조화된 필드로 옮겨 담는다).
    error_status_code: Optional[int] = None
    error_reason: Optional[str] = None


class UploadProvider(ABC):

    @abstractmethod
    def upload(self, file_path: str, metadata: dict) -> UploadResult:
        raise NotImplementedError
