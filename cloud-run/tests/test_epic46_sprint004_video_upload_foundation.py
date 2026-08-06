"""
Epic 46 Sprint 004 (RED) - Video Upload Foundation.

YouTubeUploadProvider(Sprint115, app/providers/upload/youtube_upload_
provider.py)를 실제 업로드가 가능한 구조로 확장한다 - 새 Provider
클래스를 만들지 않는다(UploadProvider Architecture 무변경).

핵심 설계: credential(OAuthCredential, Sprint002/003)을 생성자에 옵션
인자로 추가한다(기본값 None). credential이 없으면 기존 Sprint115 Stub
동작을 100% 그대로 유지한다(기존 tests/test_youtube_upload_provider.py
전부 무수정으로 통과해야 한다 - Regression Zero). credential이 있을
때만 실제 YouTube Data API(videos.insert, resumable upload)를 호출
한다. upload(file_path, metadata) 시그니처는 절대 바꾸지 않는다
(Public API 무변경).

실제 Google API 호출(googleapiclient.http.MediaFileUpload/errors.
HttpError, googleapiclient.discovery.build)은 이 테스트 전체에서
Mock 처리한다 - 실제 네트워크 호출 없음.

아직 구현이 없으므로(RED) credential 관련 테스트는 실패해야 정상.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.upload_provider import UploadResult
from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider

SAMPLE_FILE_PATH = "output/20260716_120000/final/video.mp4"
SAMPLE_METADATA = {
    "title": "제목",
    "description": "설명",
    "hashtags": ["health", "wellbeing"],
}


def _credential():
    from app.providers.upload.oauth_credential import OAuthCredential

    return OAuthCredential(
        account_id="default",
        access_token="real-access-token",
        refresh_token="real-refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


class TestExistingStubBehaviorUnaffected(unittest.TestCase):
    """credential 없이 생성하면 Sprint115 Stub 그대로 동작해야 한다
    (기존 tests/test_youtube_upload_provider.py의 회귀 재확인)."""

    def test_no_credential_still_uses_stub_success(self):
        provider = YouTubeUploadProvider()

        result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertTrue(result.success)
        self.assertTrue(result.upload_id.startswith("youtube_mock_"))

    def test_no_credential_should_fail_flag_still_works(self):
        provider = YouTubeUploadProvider(should_fail=True)

        result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertFalse(result.success)


class TestRealUploadWithCredential(unittest.TestCase):

    def _patch_youtube_api(self, video_id="real_video_123", chunk_statuses=None):
        fake_youtube = MagicMock()
        fake_request = MagicMock()

        if chunk_statuses is None:
            chunk_statuses = [(None, {"id": video_id})]

        fake_request.next_chunk.side_effect = chunk_statuses
        fake_youtube.videos.return_value.insert.return_value = fake_request

        return (
            patch(
                "app.providers.upload.youtube_upload_provider.build",
                return_value=fake_youtube,
            ),
            fake_request,
        )

    def test_uploads_via_real_youtube_api_and_returns_video_id(self):
        provider = YouTubeUploadProvider(credential=_credential())

        build_patch, fake_request = self._patch_youtube_api(video_id="real_video_123")
        with build_patch, patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ):
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertIsInstance(result, UploadResult)
        self.assertTrue(result.success)
        self.assertEqual(result.upload_id, "real_video_123")
        self.assertIn("real_video_123", result.url)
        self.assertIsNone(result.error)

    def test_maps_metadata_into_youtube_request_body(self):
        provider = YouTubeUploadProvider(credential=_credential())

        build_patch, fake_request = self._patch_youtube_api()
        with build_patch as mock_build, patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ):
            provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        fake_youtube = mock_build.return_value
        _, call_kwargs = fake_youtube.videos.return_value.insert.call_args
        body = call_kwargs["body"]

        self.assertEqual(body["snippet"]["title"], "제목")
        self.assertEqual(body["snippet"]["description"], "설명")
        self.assertEqual(body["snippet"]["tags"], ["health", "wellbeing"])
        # 기본 공개 범위는 반드시 안전한 기본값(private)이어야 한다 -
        # metadata에 명시하지 않으면 절대 실수로 공개되면 안 된다.
        self.assertEqual(body["status"]["privacyStatus"], "private")

    def test_progress_callback_invoked_per_chunk(self):
        progress_values = []

        def _on_progress(fraction):
            progress_values.append(fraction)

        provider = YouTubeUploadProvider(
            credential=_credential(), progress_callback=_on_progress
        )

        fake_status_1 = MagicMock()
        fake_status_1.progress.return_value = 0.5
        fake_status_2 = MagicMock()
        fake_status_2.progress.return_value = 1.0

        build_patch, fake_request = self._patch_youtube_api(
            chunk_statuses=[(fake_status_1, None), (fake_status_2, {"id": "vid"})],
        )
        with build_patch, patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ):
            provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertEqual(progress_values, [0.5, 1.0])

    def test_retries_on_transient_http_error_then_succeeds(self):
        from googleapiclient.errors import HttpError

        provider = YouTubeUploadProvider(credential=_credential())

        fake_resp = MagicMock()
        fake_resp.status = 503
        transient_error = HttpError(fake_resp, b"Service Unavailable")

        build_patch, fake_request = self._patch_youtube_api(
            chunk_statuses=[transient_error, (None, {"id": "recovered_video"})],
        )
        with build_patch, patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ), patch("app.providers.upload.youtube_upload_provider.time.sleep"):
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertTrue(result.success)
        self.assertEqual(result.upload_id, "recovered_video")

    def test_gives_up_after_max_retries_and_returns_failure_result(self):
        from googleapiclient.errors import HttpError

        provider = YouTubeUploadProvider(credential=_credential())

        fake_resp = MagicMock()
        fake_resp.status = 500
        persistent_error = HttpError(fake_resp, b"Internal Server Error")

        build_patch, fake_request = self._patch_youtube_api(
            chunk_statuses=[persistent_error] * 10,
        )
        with build_patch, patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ), patch("app.providers.upload.youtube_upload_provider.time.sleep"):
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertFalse(result.success)
        self.assertIsNone(result.upload_id)
        self.assertIsNotNone(result.error)

    def test_non_retryable_error_fails_immediately_without_sleep(self):
        from googleapiclient.errors import HttpError

        provider = YouTubeUploadProvider(credential=_credential())

        fake_resp = MagicMock()
        fake_resp.status = 403
        fatal_error = HttpError(fake_resp, b"Forbidden")

        build_patch, fake_request = self._patch_youtube_api(
            chunk_statuses=[fatal_error]
        )
        with build_patch, patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ), patch(
            "app.providers.upload.youtube_upload_provider.time.sleep"
        ) as mock_sleep:
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertFalse(result.success)
        mock_sleep.assert_not_called()


class TestRealUploadCapturesStructuredHttpErrorInfo(unittest.TestCase):
    """Priority 4(YouTube Shorts Auto Publish) - UploadResult.
    error_status_code/error_reason이 실제 HttpError로부터 정확히
    옮겨 담기는지 검증한다(RealYouTubeRuntime의 error_category 분류가
    이 값에 의존한다)."""

    def _patch_youtube_api(self, chunk_statuses):
        fake_youtube = MagicMock()
        fake_request = MagicMock()
        fake_request.next_chunk.side_effect = chunk_statuses
        fake_youtube.videos.return_value.insert.return_value = fake_request
        return patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        )

    def test_captures_status_code_and_reason_on_non_retryable_http_error(self):
        from googleapiclient.errors import HttpError

        fake_resp = MagicMock()
        fake_resp.status = 403
        fake_resp.reason = "Forbidden"
        fatal_error = HttpError(
            fake_resp,
            b'{"error": {"errors": [{"reason": "quotaExceeded"}], '
            b'"message": "The request cannot be completed because you have exceeded your quota."}}',
        )

        provider = YouTubeUploadProvider(credential=_credential())
        with self._patch_youtube_api([fatal_error]), patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ), patch("app.providers.upload.youtube_upload_provider.time.sleep"):
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertFalse(result.success)
        self.assertEqual(result.error_status_code, 403)
        self.assertIn("quota", result.error_reason.lower())

    def test_captures_status_code_for_generic_403_without_quota_reason(self):
        from googleapiclient.errors import HttpError

        fake_resp = MagicMock()
        fake_resp.status = 403
        fake_resp.reason = "Forbidden"
        fatal_error = HttpError(fake_resp, b"Forbidden")

        provider = YouTubeUploadProvider(credential=_credential())
        with self._patch_youtube_api([fatal_error]), patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ), patch("app.providers.upload.youtube_upload_provider.time.sleep"):
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertEqual(result.error_status_code, 403)
        self.assertNotIn("quota", (result.error_reason or "").lower())

    def test_non_http_error_leaves_status_code_and_reason_none(self):
        provider = YouTubeUploadProvider(credential=_credential())
        with self._patch_youtube_api([RuntimeError("boom")]), patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ):
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertIsNone(result.error_status_code)
        self.assertIsNone(result.error_reason)

    def test_connection_error_is_marked_with_the_connection_error_sentinel(self):
        """Priority 4, Sprint 3 - 실제 "짧은 네트워크 차단" 검증 중 발견된
        실제 Gap. 연결 자체가 실패하면(OSError 계층) HttpError가 아니라
        status_code가 없다 - 그래도 RealYouTubeRuntime이 NETWORK_ERROR로
        분류할 수 있도록 error_reason에 고정 sentinel을 남겨야 한다."""
        from app.providers.upload.youtube_upload_provider import CONNECTION_ERROR_REASON

        for exc in (
            ConnectionRefusedError("refused"),
            TimeoutError("timed out"),
            OSError("network unreachable"),
        ):
            with self.subTest(exc=type(exc).__name__):
                provider = YouTubeUploadProvider(credential=_credential())
                with self._patch_youtube_api([exc]), patch(
                    "app.providers.upload.youtube_upload_provider.MediaFileUpload",
                ):
                    result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

                self.assertFalse(result.success)
                self.assertIsNone(result.error_status_code)
                self.assertEqual(result.error_reason, CONNECTION_ERROR_REASON)

    def test_missing_local_file_is_marked_with_a_distinct_file_not_found_sentinel(self):
        """Phase 7, Sprint 3 - Retry Queue Root Cause Analysis(Sprint 2)에서
        발견: FileNotFoundError는 OSError의 하위 클래스라 지금까지는
        CONNECTION_ERROR_REASON(NETWORK_ERROR로 분류)에 함께 잡혔다 -
        로컬 원본 파일이 없을 뿐인데 "네트워크 문제"로 오분류되어 Auto
        Retry가 의미 없이 소진되는 실제 부작용이 있었다. 파일 없음은
        네트워크 오류와 명확히 구분되는 별도 sentinel이어야 한다."""
        from app.providers.upload.youtube_upload_provider import (
            CONNECTION_ERROR_REASON,
            FILE_NOT_FOUND_REASON,
        )

        provider = YouTubeUploadProvider(credential=_credential())
        with self._patch_youtube_api([FileNotFoundError(SAMPLE_FILE_PATH)]), patch(
            "app.providers.upload.youtube_upload_provider.MediaFileUpload",
        ):
            result = provider.upload(SAMPLE_FILE_PATH, SAMPLE_METADATA)

        self.assertFalse(result.success)
        self.assertIsNone(result.error_status_code)
        self.assertEqual(result.error_reason, FILE_NOT_FOUND_REASON)
        self.assertNotEqual(result.error_reason, CONNECTION_ERROR_REASON)


if __name__ == "__main__":
    unittest.main()
