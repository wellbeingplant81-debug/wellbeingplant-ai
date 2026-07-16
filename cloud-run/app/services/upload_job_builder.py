"""
Sprint120 - Upload Pipeline Integration Intelligence.

UploadJobBuilder는 개별 video output 값을 받아 Sprint109 UploadJob
모델을 조립한다. video_id/file_path/platform은 그대로 전달하고,
title/description/hashtags는 UploadJob.metadata dict로 합성한다.

이 파일이 하지 않는 것:
- file_path 추론(pipeline output 디렉터리 탐색 등) - 호출자가 이미
  완성된 file_path를 넘겨준다
- provider 생성/선택(Factory/Registry/Bootstrap 소관)
"""

from app.models.upload_job import UploadJob


class UploadJobBuilder:

    def build(
        self,
        video_id: str,
        file_path: str,
        platform: str,
        title: str,
        description: str,
        hashtags: list,
    ) -> UploadJob:

        metadata = {
            "title": title,
            "description": description,
            "hashtags": hashtags,
        }

        return UploadJob(
            video_id=video_id,
            file_path=file_path,
            platform=platform,
            metadata=metadata,
        )
