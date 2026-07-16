"""
Sprint108 - Distribution Upload Provider Foundation.

UploadProvider의 Mock 구현. 실제 네트워크 호출 없이 결정적으로
성공/실패 응답을 반환하고, 호출에 사용된 file_path/metadata를
그대로 보관해 테스트에서 전달 여부를 검증할 수 있게 한다.
"""

import os

from app.providers.upload.upload_provider import UploadProvider, UploadResult


class MockUploadProvider(UploadProvider):

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
                error="Mock upload failed",
            )

        upload_id = f"mock_upload_{os.path.basename(file_path)}"

        return UploadResult(
            success=True,
            upload_id=upload_id,
            url=f"https://mock.upload.local/{upload_id}",
            error=None,
        )
