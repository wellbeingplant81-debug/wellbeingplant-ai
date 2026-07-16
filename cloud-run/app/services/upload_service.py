"""
Sprint109 - Distribution Upload Workflow Foundation.

UploadJob을 받아 job.platform에 등록된 Sprint108 UploadProvider를
호출하는 라우팅 계층. Sprint104 platform_adapter.py(distribution 큐
아이템 → 발행 판단)와는 독립적이며, distribution_queue.py/
distribution_history.py에는 연결하지 않는다.

이 파일이 하지 않는 것:
- 실제 플랫폼 API 호출(provider 구현체 소관)
- Queue/History 기록
- 재시도/스케줄링
"""

from app.models.upload_job import UploadJob
from app.providers.upload.upload_provider import UploadResult


class UploadService:

    def __init__(self, provider_registry: dict):
        self.provider_registry = provider_registry

    def upload(self, job: UploadJob) -> UploadResult:
        provider = self.provider_registry.get(job.platform)

        if provider is None:
            raise ValueError(
                f"No upload provider registered for platform: {job.platform}"
            )

        return provider.upload(job.file_path, job.metadata)
