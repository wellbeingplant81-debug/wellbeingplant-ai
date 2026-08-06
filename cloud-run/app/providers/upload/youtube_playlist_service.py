"""
Epic 46 Sprint 006 - Metadata + Playlist.

Playlist Lookup/Create/Add Video를 담당하는 별개 Service다 -
UploadProvider Protocol(upload(file_path, metadata) -> UploadResult,
Sprint108, 무수정)을 확장하지 않는다. YouTubeUploadProvider가 필요할
때(metadata["playlist_title"])만 이 클래스를 호출한다(Best-Effort,
실패해도 영상 업로드 자체는 성공 유지).

GoogleOAuthService/YouTubeUploadProvider와 동일한 스타일 - Google API
관련 코드(build)는 이 파일 안에서만 쓴다. Access Token 갱신은 이
클래스의 책임이 아니다(CredentialLoader가 이미 보장).
"""

from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build

_MAX_LOOKUP_RESULTS = 50


class YouTubePlaylistService:

    def __init__(self, credential):
        self.credential = credential

    def _client(self):
        google_credentials = GoogleCredentials(token=self.credential.access_token)
        return build("youtube", "v3", credentials=google_credentials)

    def find_playlist_by_title(self, title: str):
        youtube = self._client()
        response = (
            youtube.playlists()
            .list(part="snippet", mine=True, maxResults=_MAX_LOOKUP_RESULTS)
            .execute()
        )

        for item in response.get("items") or []:
            if item.get("snippet", {}).get("title") == title:
                return item["id"]

        return None

    def create_playlist(
        self, title: str, description: str = "", privacy_status: str = "private"
    ) -> str:
        youtube = self._client()
        response = (
            youtube.playlists()
            .insert(
                part="snippet,status",
                body={
                    "snippet": {"title": title, "description": description},
                    "status": {"privacyStatus": privacy_status},
                },
            )
            .execute()
        )

        return response["id"]

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> None:
        youtube = self._client()
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                },
            },
        ).execute()

    def get_or_create_playlist(self, title: str) -> str:
        existing = self.find_playlist_by_title(title)
        if existing is not None:
            return existing

        return self.create_playlist(title)
