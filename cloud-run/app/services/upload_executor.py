"""
Sprint110 - Distribution Upload Execution Intelligence.

Sprint109 UploadService.upload(job)의 UploadResult를 UploadExecution
레코드로 정규화하는 실행 계층. Sprint104 platform_adapter.py(distribution
큐 아이템 → 발행 판단)와는 독립적이며, distribution_queue.py/
distribution_history.py에는 연결하지 않는다.

이 파일이 하지 않는 것:
- 실행 결과 저장(store/history 소관, 이번 스프린트 범위 밖)
- 재시도/스케줄링
"""

from app.models.upload_execution import UploadExecution, UploadStatus
from app.models.upload_job import UploadJob


class UploadExecutor:

    def __init__(self, upload_service):
        self.upload_service = upload_service

    def execute(self, job: UploadJob) -> UploadExecution:
        result = self.upload_service.upload(job)

        status = UploadStatus.SUCCESS if result.success else UploadStatus.FAILED

        return UploadExecution(
            video_id=job.video_id,
            platform=job.platform,
            status=status,
            upload_id=result.upload_id,
            url=result.url,
            error=result.error,
        )
