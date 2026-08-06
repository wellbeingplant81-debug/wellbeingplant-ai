"""
Epic 46 Sprint 005 (RED) - Thumbnail + Scheduled Publish.

YouTubeUploadProvider(Sprint004, 무수정 그대로 유지되는 부분과 확장되는
부분이 나뉜다)에 Thumbnail Upload/예약 공개(PublishAt)를 추가한다.
upload(file_path, metadata) 시그니처는 그대로다 - metadata dict가
받아들이는 선택적 키(thumbnail_path/publish_at)만 늘어난다.

UploadResult에는 thumbnail_error(선택, 기본 None)만 추가한다 - 기존
4개 필드 기반 호출부는 전혀 영향받지 않는다(Additive, Public API
최소 변경). Thumbnail 업로드 실패는 영상 업로드 자체의 success를
바꾸지 않는다 - 영상은 이미 성공적으로 올라갔기 때문이다.

YouTube API 규칙: 예약 공개(publishAt)는 반드시 privacyStatus=private
상태에서만 동작한다 - publish_at이 주어지면 metadata의 다른
privacy_status 값과 무관하게 private로 강제한다.

아직 구현이 없으므로(RED) 새 동작에 대한 테스트는 실패해야 정상.
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

from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider

SAMPLE_FILE_PATH = "output/20260716_120000/final/video.mp4"


def _credential():
    from app.providers.upload.oauth_credential import OAuthCredential

    return OAuthCredential(
        account_id="default",
        access_token="real-access-token",
        refresh_token="real-refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


class _FakeYouTubeApi:
    """videos().insert()/thumbnails().set() 둘 다 지원하는 Fake."""

    def __init__(self, video_id="vid_123", thumbnail_should_fail=False):
        self.video_id = video_id
        self.thumbnail_should_fail = thumbnail_should_fail
        self.thumbnail_calls = []
        self.insert_call_kwargs = None

    def videos(self):
        api = MagicMock()

        def _insert(**kwargs):
            self.insert_call_kwargs = kwargs
            request = MagicMock()
            request.next_chunk.side_effect = [(None, {"id": self.video_id})]
            return request

        api.insert.side_effect = _insert
        return api

    def thumbnails(self):
        api = MagicMock()

        def _set(**kwargs):
            self.thumbnail_calls.append(kwargs)
            execute_mock = MagicMock()
            if self.thumbnail_should_fail:
                execute_mock.execute.side_effect = RuntimeError(
                    "thumbnail upload failed"
                )
            else:
                execute_mock.execute.return_value = {}
            return execute_mock

        api.set.side_effect = _set
        return api


class TestThumbnailUpload(unittest.TestCase):

    def test_uploads_thumbnail_after_successful_video_upload(self):
        fake_youtube = _FakeYouTubeApi(video_id="vid_with_thumb")
        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"):
            result = provider.upload(
                SAMPLE_FILE_PATH,
                {"title": "t", "thumbnail_path": "output/thumb.jpg"},
            )

        self.assertTrue(result.success)
        self.assertEqual(result.upload_id, "vid_with_thumb")
        self.assertEqual(len(fake_youtube.thumbnail_calls), 1)
        self.assertEqual(fake_youtube.thumbnail_calls[0]["videoId"], "vid_with_thumb")
        self.assertIsNone(result.thumbnail_error)

    def test_skips_thumbnail_call_when_not_provided(self):
        fake_youtube = _FakeYouTubeApi(video_id="vid_no_thumb")
        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"):
            result = provider.upload(SAMPLE_FILE_PATH, {"title": "t"})

        self.assertTrue(result.success)
        self.assertEqual(len(fake_youtube.thumbnail_calls), 0)
        self.assertIsNone(result.thumbnail_error)

    def test_thumbnail_failure_does_not_fail_video_upload(self):
        fake_youtube = _FakeYouTubeApi(
            video_id="vid_thumb_fail", thumbnail_should_fail=True
        )
        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"):
            result = provider.upload(
                SAMPLE_FILE_PATH,
                {"title": "t", "thumbnail_path": "output/thumb.jpg"},
            )

        self.assertTrue(result.success)
        self.assertEqual(result.upload_id, "vid_thumb_fail")
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.thumbnail_error)


class TestScheduledPublish(unittest.TestCase):

    def test_publish_at_datetime_sets_iso_timestamp_and_forces_private(self):
        fake_youtube = _FakeYouTubeApi(video_id="vid_scheduled")
        provider = YouTubeUploadProvider(credential=_credential())

        publish_at = datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc)

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"):
            result = provider.upload(
                SAMPLE_FILE_PATH,
                {"title": "t", "publish_at": publish_at, "privacy_status": "public"},
            )

        self.assertTrue(result.success)
        body = fake_youtube.insert_call_kwargs["body"]
        self.assertEqual(body["status"]["publishAt"], "2026-08-01T09:00:00Z")
        # YouTube 규칙 - 예약 발행은 private 상태에서만 동작하므로,
        # metadata가 public을 요청했어도 private로 강제되어야 한다.
        self.assertEqual(body["status"]["privacyStatus"], "private")

    def test_publish_at_iso_string_passthrough(self):
        fake_youtube = _FakeYouTubeApi(video_id="vid_scheduled_str")
        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"):
            provider.upload(
                SAMPLE_FILE_PATH,
                {"title": "t", "publish_at": "2026-09-01T00:00:00Z"},
            )

        body = fake_youtube.insert_call_kwargs["body"]
        self.assertEqual(body["status"]["publishAt"], "2026-09-01T00:00:00Z")

    def test_no_publish_at_leaves_status_untouched(self):
        fake_youtube = _FakeYouTubeApi(video_id="vid_no_schedule")
        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"):
            provider.upload(
                SAMPLE_FILE_PATH, {"title": "t", "privacy_status": "unlisted"}
            )

        body = fake_youtube.insert_call_kwargs["body"]
        self.assertNotIn("publishAt", body["status"])
        self.assertEqual(body["status"]["privacyStatus"], "unlisted")


class TestSprint004RegressionUnaffected(unittest.TestCase):

    def test_upload_without_new_options_behaves_as_before(self):
        fake_youtube = _FakeYouTubeApi(video_id="vid_plain")
        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"):
            result = provider.upload(
                SAMPLE_FILE_PATH, {"title": "t", "description": "d"}
            )

        self.assertTrue(result.success)
        self.assertEqual(result.upload_id, "vid_plain")
        body = fake_youtube.insert_call_kwargs["body"]
        self.assertEqual(body["status"]["privacyStatus"], "private")

    def test_stub_mode_still_works_without_credential(self):
        provider = YouTubeUploadProvider()

        result = provider.upload(SAMPLE_FILE_PATH, {"title": "t"})

        self.assertTrue(result.success)
        self.assertIsNone(result.thumbnail_error)


if __name__ == "__main__":
    unittest.main()
