"""
Sprint115 - YouTube Upload Provider Foundation.

Sprint108 UploadProvider 인터페이스를 구현하는 YouTube 전용 구체
클래스. 실제 YouTube API/OAuth/Token은 전혀 다루지 않는다 - 결정적으로
성공/실패를 반환하는 stub 구현이며, 실제 연동은 이후 스프린트 범위다.
"""

import os

from app.providers.upload.upload_provider import UploadProvider, UploadResult


class YouTubeUploadProvider(UploadProvider):

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.last_file_path = None
        self.last_metadata = None

    def upload(self, file_path: str, metadata: dict) -> UploadResult:
        self.last_file_path = file_path
        self.last_metadata = metadata

        if self.should_fail:
            return UploadResult(
                success=False, upload_id=None, url=None,
                error="YouTube mock upload failed",
            )

        upload_id = f"youtube_mock_{os.path.basename(file_path)}"

        return UploadResult(
            success=True,
            upload_id=upload_id,
            url=f"https://mock.youtube.upload.local/{upload_id}",
            error=None,
        )
