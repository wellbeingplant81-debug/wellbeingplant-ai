"""
Sprint109 - Distribution Upload Workflow Foundation.
Sprint117 - Upload Service Provider Registry Integration.

UploadJob을 받아 job.platform에 등록된 Sprint108 UploadProvider를
호출하는 라우팅 계층. Sprint104 platform_adapter.py(distribution 큐
아이템 → 발행 판단)와는 독립적이며, distribution_queue.py/
distribution_history.py에는 연결하지 않는다.

provider_registry는 Sprint116 UploadProviderRegistry 인스턴스 또는
dict(하위 호환)를 받는다 - 어느 쪽으로 생성해도 내부적으로는 항상
UploadProviderRegistry 하나의 타입으로 정규화해서 저장한다. Registry가
provider 선택의 공식 계층이 된다.

이 파일이 하지 않는 것:
- 실제 플랫폼 API 호출(provider 구현체 소관)
- Queue/History 기록
- 재시도/스케줄링
"""

from app.models.upload_job import UploadJob
from app.providers.upload.provider_registry import UploadProviderRegistry
from app.providers.upload.upload_provider import UploadResult


class UploadService:

    def __init__(self, provider_registry):
        if isinstance(provider_registry, UploadProviderRegistry):
            self.provider_registry = provider_registry
        else:
            registry = UploadProviderRegistry()
            for platform, provider in provider_registry.items():
                registry.register(platform, provider)
            self.provider_registry = registry

    def upload(self, job: UploadJob) -> UploadResult:
        provider = self.provider_registry.get(job.platform)

        if provider is None:
            raise ValueError(
                f"No upload provider registered for platform: {job.platform}"
            )

        return provider.upload(job.file_path, job.metadata)
