"""
Sprint115 - YouTube Upload Provider Foundation.
Epic 46 Sprint 004 - Video Upload Foundation.
Epic 46 Sprint 005 - Thumbnail + Scheduled Publish.

Sprint108 UploadProvider 인터페이스를 구현하는 YouTube 전용 구체
클래스. credential(OAuthCredential, Epic46 Sprint002/003)이 주어지지
않으면 Sprint115의 결정적 Stub 동작을 100% 그대로 유지한다(Regression
Zero - 기존 tests/test_youtube_upload_provider.py 전부 무수정 통과).
credential이 주어질 때만 실제 YouTube Data API(videos.insert, resumable
upload)를 호출한다. upload(file_path, metadata) 시그니처는 절대
바꾸지 않는다(Public API 무변경) - Thumbnail/예약 공개는 metadata
dict가 받아들이는 선택적 키(thumbnail_path/publish_at)만 늘려서
지원한다.

Google API 관련 코드(build/MediaFileUpload/HttpError)는 이 파일
안에서만 쓴다 - Service Layer(이 클래스 자체) 뒤에 숨긴다.

Access Token 갱신은 이 클래스의 책임이 아니다 - CredentialLoader
(Sprint002, 무수정)가 upload() 호출 전에 이미 유효한 Credential을
보장한다는 전제다. 그래서 여기서는 client_id/client_secret 없이
access_token만으로 google Credentials를 구성한다(OAuth 설정을
Upload Provider에 노출하지 않는다).

Thumbnail 업로드 실패는 영상 업로드 자체의 success를 바꾸지 않는다 -
영상은 이미 성공적으로 올라갔기 때문이다(UploadResult.thumbnail_error
에만 기록). YouTube API 규칙상 예약 공개(publishAt)는 반드시
privacyStatus=private 상태에서만 동작하므로, publish_at이 주어지면
metadata의 다른 privacy_status 값과 무관하게 private로 강제한다.
"""

import os
import time
from datetime import datetime
from typing import Optional

from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.providers.upload.upload_provider import UploadProvider, UploadResult

_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 1

# Priority 4, Sprint 3 - OSError(연결 자체 실패, status_code 없음)를
# 실은 UploadResult.error_reason의 고정 sentinel. real_youtube_runtime.
# py의 _classify_upload_error()가 이 정확한 문자열을 확인해 NETWORK_
# ERROR로 분류한다(실제 Google 응답 문구와 절대 겹치지 않도록 대문자
# 스네이크 케이스로 - Google reason은 항상 자연어 문장이다).
CONNECTION_ERROR_REASON = "CONNECTION_ERROR"

# Phase 7, Sprint 3 - FileNotFoundError(OSError의 하위 클래스) 전용
# sentinel. CONNECTION_ERROR_REASON과 절대 겹치지 않도록 별도 문자열을
# 쓴다 - real_youtube_runtime.py의 _classify_upload_error()가 이 값만
# 보고 "FILE_NOT_FOUND"로 분류한다(NETWORK_ERROR와 다르게, 이 카테고리는
# 자동 재시도 허용 목록에 절대 포함되면 안 된다 - 재시도해도 파일이
# 다시 생기지 않는다).
FILE_NOT_FOUND_REASON = "FILE_NOT_FOUND"

# Epic 46 Sprint 006 - Default Metadata. categoryId "22"는 YouTube
# 표준 카테고리 "People & Blogs" - 이 프로젝트의 건강 정보 콘텐츠에
# 합리적인 기본값이다. language 기본값은 이 프로젝트가 한국어
# 콘텐츠이므로 "ko".
_DEFAULT_CATEGORY_ID = "22"
_DEFAULT_LANGUAGE = "ko"
_DEFAULT_TITLE = "Untitled"


def _normalize_publish_at(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


def _map_metadata_to_youtube_body(metadata: dict) -> dict:
    status = {
        # 안전한 기본값 - metadata가 명시하지 않으면 절대 실수로
        # 공개(public)되지 않는다.
        "privacyStatus": metadata.get("privacy_status", "private"),
    }

    publish_at = metadata.get("publish_at")
    if publish_at:
        status["publishAt"] = _normalize_publish_at(publish_at)
        # YouTube 규칙 - 예약 공개는 private 상태에서만 동작한다.
        status["privacyStatus"] = "private"

    return {
        "snippet": {
            "title": metadata.get("title") or _DEFAULT_TITLE,
            "description": metadata.get("description", ""),
            "tags": metadata.get("hashtags") or metadata.get("tags") or [],
            "categoryId": metadata.get("category_id", _DEFAULT_CATEGORY_ID),
            "defaultLanguage": metadata.get("language", _DEFAULT_LANGUAGE),
        },
        "status": status,
    }


class YouTubeUploadProvider(UploadProvider):

    def __init__(
        self, credential=None, should_fail: bool = False, progress_callback=None
    ):
        self.credential = credential
        self.should_fail = should_fail
        self.progress_callback = progress_callback
        self.last_file_path: Optional[str] = None
        self.last_metadata: Optional[dict] = None

    def upload(self, file_path: str, metadata: dict) -> UploadResult:
        self.last_file_path = file_path
        self.last_metadata = metadata

        if self.should_fail:
            return UploadResult(
                success=False,
                upload_id=None,
                url=None,
                error="YouTube mock upload failed",
            )

        if self.credential is None:
            return self._stub_upload(file_path)

        return self._real_upload(file_path, metadata)

    def _stub_upload(self, file_path: str) -> UploadResult:
        upload_id = f"youtube_mock_{os.path.basename(file_path)}"

        return UploadResult(
            success=True,
            upload_id=upload_id,
            url=f"https://mock.youtube.upload.local/{upload_id}",
            error=None,
        )

    def _real_upload(self, file_path: str, metadata: dict) -> UploadResult:
        try:
            youtube = build(
                "youtube",
                "v3",
                credentials=GoogleCredentials(token=self.credential.access_token),
            )
            body = _map_metadata_to_youtube_body(metadata)
            media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media,
            )

            response = self._execute_with_retry(request)
            video_id = response["id"]
        except HttpError as exc:
            # Priority 4 - HttpError는 status_code/reason을 이미 실제로
            # 계산해 갖고 있다(googleapiclient 자체 구현) - 지어내지
            # 않고 그대로 옮겨 담는다. 일반 Exception 분기보다 먼저
            # 와야 한다(HttpError도 Exception의 하위 클래스라 순서가
            # 중요하다).
            return UploadResult(
                success=False, upload_id=None, url=None, error=str(exc),
                error_status_code=exc.resp.status, error_reason=exc.reason,
            )
        except FileNotFoundError as exc:
            # Phase 7, Sprint 3 - Retry Queue Root Cause Analysis(Sprint 2)
            # 에서 발견된 실제 Gap: FileNotFoundError는 OSError의
            # 하위 클래스라 지금까지는 except OSError 분기에 함께
            # 잡혀 CONNECTION_ERROR_REASON(NETWORK_ERROR로 분류)이
            # 됐다 - 로컬 원본 파일이 없을 뿐인데 "네트워크 문제"로
            # 오분류되어 Auto Retry가 의미 없이 소진되는 실제 부작용이
            # 있었다. OSError보다 먼저 잡아 별도 sentinel로 표시한다
            # (FileNotFoundError가 OSError의 하위 클래스라 순서가
            # 중요하다).
            return UploadResult(
                success=False, upload_id=None, url=None, error=str(exc),
                error_status_code=None, error_reason=FILE_NOT_FOUND_REASON,
            )
        except OSError as exc:
            # Priority 4, Sprint 3 - 실제 "짧은 네트워크 차단" 검증 중
            # 발견된 실제 Gap: 연결 자체가 실패하면(DNS 실패/Connection
            # Refused/Timeout 등 - Python 3에서 전부 OSError 계층) HTTP
            # 응답 자체를 받지 못하므로 HttpError가 아니다(status_code가
            # 없다) - 이전에는 이 경우가 일반 Exception 분기로 떨어져
            # UNKNOWN_ERROR로 잘못 분류됐다(자동 재시도 대상에서 제외돼
            # 버림). status_code 없이도 "연결 자체가 안 됐다"는 사실
            # 하나만으로 이미 네트워크 문제라고 확신할 수 있으므로,
            # error_reason에 고정 sentinel을 남겨 RealYouTubeRuntime이
            # 곧장 NETWORK_ERROR로 분류하게 한다.
            return UploadResult(
                success=False, upload_id=None, url=None, error=str(exc),
                error_status_code=None, error_reason=CONNECTION_ERROR_REASON,
            )
        except Exception as exc:
            return UploadResult(success=False, upload_id=None, url=None, error=str(exc))

        thumbnail_error = None
        thumbnail_path = metadata.get("thumbnail_path")
        if thumbnail_path:
            thumbnail_error = self._upload_thumbnail(youtube, video_id, thumbnail_path)

        playlist_error = None
        playlist_title = metadata.get("playlist_title")
        if playlist_title:
            playlist_error = self._add_to_playlist(video_id, playlist_title)

        return UploadResult(
            success=True,
            upload_id=video_id,
            url=f"https://youtu.be/{video_id}",
            error=None,
            thumbnail_error=thumbnail_error,
            playlist_error=playlist_error,
        )

    def _add_to_playlist(self, video_id: str, playlist_title: str) -> Optional[str]:
        try:
            # 지연 import - Playlist는 Best-Effort 부가 기능이라 필요할
            # 때만 youtube_playlist_service를 가져온다(기존 Sprint004/
            # 005 경로에는 아무 영향이 없다).
            from app.providers.upload.youtube_playlist_service import (
                YouTubePlaylistService,
            )

            playlist_service = YouTubePlaylistService(credential=self.credential)
            playlist_id = playlist_service.get_or_create_playlist(playlist_title)
            playlist_service.add_video_to_playlist(playlist_id, video_id)
            return None
        except Exception as exc:
            return str(exc)

    def _upload_thumbnail(
        self, youtube, video_id: str, thumbnail_path: str
    ) -> Optional[str]:
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path),
            ).execute()
            return None
        except Exception as exc:
            return str(exc)

    def _execute_with_retry(self, request):
        response = None
        retries = 0

        while response is None:
            try:
                status, response = request.next_chunk()
                if status is not None and self.progress_callback is not None:
                    self.progress_callback(status.progress())
            except HttpError as exc:
                if (
                    exc.resp.status in _RETRYABLE_STATUS_CODES
                    and retries < _MAX_RETRIES
                ):
                    retries += 1
                    time.sleep(_RETRY_BACKOFF_SECONDS * retries)
                    continue
                raise

        return response
