"""
Epic 46 Sprint 006 (RED) - Metadata + Playlist.

Title/Description/Tags는 Sprint004에서 이미 구현됨(무수정). 이번
Sprint는 Category/Language/Default Metadata를 _map_metadata_to_
youtube_body()에 추가하고, Playlist Lookup/Create/Add Video를 새
YouTubePlaylistService(YouTubeUploadProvider와 나란한 별개 클래스 -
UploadProvider Protocol을 확장하지 않는다)로 구현한다.

YouTubeUploadProvider.upload()는 metadata["playlist_title"]이 주어질
때만 업로드 후 Playlist에 추가한다(Thumbnail과 동일한 Best-Effort
패턴 - 실패해도 영상 업로드 자체는 성공으로 유지, UploadResult.
playlist_error에만 기록). upload() 시그니처는 그대로다.

아직 구현이 없으므로(RED) 새 클래스/필드에 대한 테스트는 실패해야 정상.
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

from app.providers.upload.youtube_upload_provider import (
    YouTubeUploadProvider,
    _map_metadata_to_youtube_body,
)

SAMPLE_FILE_PATH = "output/20260716_120000/final/video.mp4"


def _credential():
    from app.providers.upload.oauth_credential import OAuthCredential

    return OAuthCredential(
        account_id="default",
        access_token="real-access-token",
        refresh_token="real-refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


class TestDefaultMetadata(unittest.TestCase):

    def test_default_category_and_language_applied_when_not_specified(self):
        body = _map_metadata_to_youtube_body({"title": "t"})

        self.assertIn("categoryId", body["snippet"])
        self.assertIn("defaultLanguage", body["snippet"])
        self.assertTrue(body["snippet"]["categoryId"])
        self.assertTrue(body["snippet"]["defaultLanguage"])

    def test_explicit_category_and_language_override_defaults(self):
        body = _map_metadata_to_youtube_body(
            {"title": "t", "category_id": "27", "language": "en"},
        )

        self.assertEqual(body["snippet"]["categoryId"], "27")
        self.assertEqual(body["snippet"]["defaultLanguage"], "en")

    def test_missing_title_falls_back_to_default(self):
        body = _map_metadata_to_youtube_body({})

        self.assertTrue(body["snippet"]["title"])


class TestYouTubePlaylistServiceLookup(unittest.TestCase):

    def test_find_playlist_by_title_found(self):
        from app.providers.upload.youtube_playlist_service import YouTubePlaylistService

        fake_youtube = MagicMock()
        fake_youtube.playlists.return_value.list.return_value.execute.return_value = {
            "items": [
                {"id": "PL_other", "snippet": {"title": "다른 재생목록"}},
                {"id": "PL_target", "snippet": {"title": "건강 정보"}},
            ],
        }

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=fake_youtube,
        ):
            service = YouTubePlaylistService(credential=_credential())
            playlist_id = service.find_playlist_by_title("건강 정보")

        self.assertEqual(playlist_id, "PL_target")

    def test_find_playlist_by_title_not_found_returns_none(self):
        from app.providers.upload.youtube_playlist_service import YouTubePlaylistService

        fake_youtube = MagicMock()
        fake_youtube.playlists.return_value.list.return_value.execute.return_value = {
            "items": []
        }

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=fake_youtube,
        ):
            service = YouTubePlaylistService(credential=_credential())
            playlist_id = service.find_playlist_by_title("존재하지 않음")

        self.assertIsNone(playlist_id)


class TestYouTubePlaylistServiceCreate(unittest.TestCase):

    def test_create_playlist_returns_new_id(self):
        from app.providers.upload.youtube_playlist_service import YouTubePlaylistService

        fake_youtube = MagicMock()
        fake_youtube.playlists.return_value.insert.return_value.execute.return_value = {
            "id": "PL_new",
        }

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=fake_youtube,
        ):
            service = YouTubePlaylistService(credential=_credential())
            playlist_id = service.create_playlist("새 재생목록")

        self.assertEqual(playlist_id, "PL_new")
        _, kwargs = fake_youtube.playlists.return_value.insert.call_args
        self.assertEqual(kwargs["body"]["snippet"]["title"], "새 재생목록")


class TestYouTubePlaylistServiceAddVideo(unittest.TestCase):

    def test_add_video_to_playlist_calls_playlist_items_insert(self):
        from app.providers.upload.youtube_playlist_service import YouTubePlaylistService

        fake_youtube = MagicMock()

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=fake_youtube,
        ):
            service = YouTubePlaylistService(credential=_credential())
            service.add_video_to_playlist("PL_target", "vid_123")

        _, kwargs = fake_youtube.playlistItems.return_value.insert.call_args
        resource_id = kwargs["body"]["snippet"]["resourceId"]
        self.assertEqual(kwargs["body"]["snippet"]["playlistId"], "PL_target")
        self.assertEqual(resource_id["videoId"], "vid_123")


class TestYouTubePlaylistServiceGetOrCreate(unittest.TestCase):

    def test_reuses_existing_playlist_when_found(self):
        from app.providers.upload.youtube_playlist_service import YouTubePlaylistService

        fake_youtube = MagicMock()
        fake_youtube.playlists.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "PL_existing", "snippet": {"title": "건강 정보"}}],
        }

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=fake_youtube,
        ):
            service = YouTubePlaylistService(credential=_credential())
            playlist_id = service.get_or_create_playlist("건강 정보")

        self.assertEqual(playlist_id, "PL_existing")
        fake_youtube.playlists.return_value.insert.assert_not_called()

    def test_creates_playlist_when_not_found(self):
        from app.providers.upload.youtube_playlist_service import YouTubePlaylistService

        fake_youtube = MagicMock()
        fake_youtube.playlists.return_value.list.return_value.execute.return_value = {
            "items": []
        }
        fake_youtube.playlists.return_value.insert.return_value.execute.return_value = {
            "id": "PL_brand_new",
        }

        with patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=fake_youtube,
        ):
            service = YouTubePlaylistService(credential=_credential())
            playlist_id = service.get_or_create_playlist("새 카테고리")

        self.assertEqual(playlist_id, "PL_brand_new")


class TestYouTubeUploadProviderPlaylistIntegration(unittest.TestCase):

    def _fake_youtube_with_video(self, video_id="vid_playlist"):
        fake_youtube = MagicMock()
        request = MagicMock()
        request.next_chunk.side_effect = [(None, {"id": video_id})]
        fake_youtube.videos.return_value.insert.return_value = request
        return fake_youtube

    def test_adds_uploaded_video_to_playlist_when_playlist_title_given(self):
        fake_youtube = self._fake_youtube_with_video(video_id="vid_for_playlist")
        fake_youtube.playlists.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "PL_health", "snippet": {"title": "건강 정보"}}],
        }

        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"), patch(
            "app.providers.upload.youtube_playlist_service.build",
            return_value=fake_youtube,
        ):
            result = provider.upload(
                SAMPLE_FILE_PATH, {"title": "t", "playlist_title": "건강 정보"}
            )

        self.assertTrue(result.success)
        self.assertIsNone(result.playlist_error)
        _, kwargs = fake_youtube.playlistItems.return_value.insert.call_args
        self.assertEqual(
            kwargs["body"]["snippet"]["resourceId"]["videoId"], "vid_for_playlist"
        )

    def test_no_playlist_title_skips_playlist_calls_entirely(self):
        fake_youtube = self._fake_youtube_with_video(video_id="vid_no_playlist")

        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"):
            result = provider.upload(SAMPLE_FILE_PATH, {"title": "t"})

        self.assertTrue(result.success)
        self.assertIsNone(result.playlist_error)
        fake_youtube.playlistItems.return_value.insert.assert_not_called()

    def test_playlist_failure_does_not_fail_video_upload(self):
        fake_youtube = self._fake_youtube_with_video(video_id="vid_playlist_fail")

        provider = YouTubeUploadProvider(credential=_credential())

        with patch(
            "app.providers.upload.youtube_upload_provider.build",
            return_value=fake_youtube,
        ), patch("app.providers.upload.youtube_upload_provider.MediaFileUpload"), patch(
            "app.providers.upload.youtube_playlist_service.build",
            side_effect=RuntimeError("playlist API error"),
        ):
            result = provider.upload(
                SAMPLE_FILE_PATH, {"title": "t", "playlist_title": "건강 정보"}
            )

        self.assertTrue(result.success)
        self.assertEqual(result.upload_id, "vid_playlist_fail")
        self.assertIsNotNone(result.playlist_error)


class TestSprint004And005RegressionUnaffected(unittest.TestCase):

    def test_stub_mode_still_works(self):
        provider = YouTubeUploadProvider()

        result = provider.upload(SAMPLE_FILE_PATH, {"title": "t"})

        self.assertTrue(result.success)
        self.assertIsNone(result.playlist_error)


if __name__ == "__main__":
    unittest.main()
