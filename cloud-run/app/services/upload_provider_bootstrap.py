"""
Sprint119 - Upload Provider Bootstrap Intelligence.

Sprint118 UploadProviderFactory + Sprint116 UploadProviderRegistry +
Sprint109/117 UploadService를 조립하는 계층이다. 새 provider 생성/
선택 로직은 추가하지 않고 기존 3개 계층을 연결만 한다.

이 파일이 하지 않는 것:
- provider 생성/선택 로직(Factory/Registry 소관)
- Executor/Retry/Distribution 연결
"""

from app.providers.upload.provider_factory import UploadProviderFactory
from app.providers.upload.provider_registry import UploadProviderRegistry
from app.services.upload_service import UploadService


class UploadProviderBootstrap:

    def create_registry(self) -> UploadProviderRegistry:
        return UploadProviderFactory().build_registry()

    def create_upload_service(self) -> UploadService:
        registry = self.create_registry()
        return UploadService(provider_registry=registry)
