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


@dataclass
class UploadResult:
    success: bool
    upload_id: str
    url: str
    error: str


class UploadProvider(ABC):

    @abstractmethod
    def upload(self, file_path: str, metadata: dict) -> UploadResult:
        raise NotImplementedError
