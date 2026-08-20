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
        """
        그 이름의 재생목록을 찾는다. 없으면 None.

        뒤 장까지 본다. 한 번에 오는 것은 최대 50 개라, 첫 장만 보면
        51 번째의 이름이 "없다" 로 읽힌다 - 그리고 그 답을 받은
        get_or_create_playlist 는 같은 이름을 하나 더 만든다. 찾지
        못해서 만드는 것이지 없어서 만드는 것이 아니다.

        Sprint252 가 playlistItems 쪽에 놓은 걸음과 같은 모양이다.
        한쪽만 고치면 다른 쪽이 언젠가 같은 결함으로 돌아간다.

        찾으면 거기서 멈춘다 - 뒤에 장이 남아 있어도 더 묻지 않는다.
        같은 이름이 여럿이면 먼저 만난 것이고, 장이 늘어도 그 차례는
        그대로다.
        """

        youtube = self._client()

        token = None

        while True:
            asked = {"part": "snippet", "mine": True,
                     "maxResults": _MAX_LOOKUP_RESULTS}

            if token:
                asked["pageToken"] = token

            response = youtube.playlists().list(**asked).execute()

            for item in response.get("items") or []:
                if item.get("snippet", {}).get("title") == title:
                    return item["id"]

            token = response.get("nextPageToken")

            # 글자일 때만 다음 장이 있다. 이 자리를 느슨하게 두면 시험의
            # 가짜 객체가 무엇이든 돌려줄 때 여기서 영원히 돈다.
            if not isinstance(token, str) or not token:
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

    def already_in_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        그 재생목록에 그 영상이 이미 있는가.

        둘이 동시에 맞을 때만 참이다 - 다른 재생목록에 같은 영상이
        드는 것은 정상이고, 중복이 아니다.

        뒤 페이지까지 본다. 한 번에 오는 것은 최대 50 개라, 첫 장만
        보고 "없다" 고 하면 큰 재생목록에서는 매번 중복이 쌓인다.

        읽지 못하면 그대로 올려 보낸다. 모르는 채로 "없다" 고 하면
        그것이 곧 중복이 된다.
        """

        youtube = self._client()

        token = None

        while True:
            asked = {"part": "snippet", "playlistId": playlist_id,
                     "maxResults": _MAX_LOOKUP_RESULTS}

            if token:
                asked["pageToken"] = token

            response = youtube.playlistItems().list(**asked).execute()

            for item in response.get("items") or []:
                resource = item.get("snippet", {}).get("resourceId", {})

                if resource.get("videoId") == video_id:
                    return True

            token = response.get("nextPageToken")

            # 글자일 때만 다음 장이 있다. 이 자리를 느슨하게 두면 시험의
            # 가짜 객체가 무엇이든 돌려줄 때 여기서 영원히 돈다.
            if not isinstance(token, str) or not token:
                return False

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        그 영상을 재생목록에 넣는다. 이미 있으면 넣지 않는다.

        올린 뒤의 이 걸음은 다시 눌릴 수 있다(재시도 · 줄 다시
        세우기). YouTube 는 같은 영상이 한 재생목록에 여러 번 드는
        것을 막지 않으므로, 확인하지 않으면 누를 때마다 항목이 하나씩
        더 생긴다.

        돌려주는 것은 "넣었는가" 다. 예전에는 None 이었고 부르는 쪽은
        예외만 보았다 - 그 계약은 그대로다(예외가 없으면 성공).
        """

        if self.already_in_playlist(playlist_id, video_id):
            return False

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

        return True

    def get_or_create_playlist(self, title: str) -> str:
        existing = self.find_playlist_by_title(title)
        if existing is not None:
            return existing

        return self.create_playlist(title)
