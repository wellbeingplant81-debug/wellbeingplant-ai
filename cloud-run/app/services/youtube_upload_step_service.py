"""
Sprint91 - Upload Runtime 이식 (Porting Phase 4).

OneDrive 저장소의 app/services/youtube_upload_step_service.py(Epic46
Sprint008)를 가져왔다. 새 OAuth/Upload 로직을 만들지 않는다 -
GoogleOAuthService/FileTokenStore/CredentialLoader/YouTubeUploadProvider
(Sprint89 이식, 전부 무수정)를 조립만 한다.

원본과 다른 곳이 세 군데다. 전부 이 저장소의 사실이 원본과 달라서 생긴
것이고, 하나씩 이유가 있다.

1. render_profile을 쓰지 않는다.

   원본은 render_profile.py(shorts/longform 축)로 파일명을 골랐다. 이
   저장소의 엔진은 longform을 만들지 않는다 - final_video_service는
   final_short.mp4를, thumbnail은 thumbnail.png를 하드코딩한다.
   render_profile을 같이 가져오면 이 엔진이 못 만드는 산출물
   (final_longform.mp4)을 가리키는 축이 생기고, 나중에 누군가 그것을
   실제 설정으로 오해한다. 그래서 studio_service가 이미 갖고 있는
   MEDIA_KINDS(이 저장소에서 산출물 이름을 적어 둔 유일한 자리)를
   그대로 읽는다 - 엔진이 이름을 바꾸면 업로드도 같이 따라간다.

   기본 경로의 결과는 원본과 완전히 같다. render_profile=None일 때
   원본이 고르는 이름이 정확히 final_short.mp4 / thumbnail.png다.

2. ENABLE_YOUTUBE_UPLOAD로 막는다.

   RealYouTubeRuntime.login()이 원본에서 이미 이 플래그로 막고 있다.
   Step은 Runtime을 거치지 않고 자격증명 체인을 직접 타므로, 같은
   플래그를 여기에도 두지 않으면 Runtime만 막히고 Step은 열려 있는
   구멍이 된다. 실제 업로드는 이 저장소에서 아직 한 번도 검증되지
   않았다.

3. 업로드 전에 OAuth 상태를 먼저 본다.

   credential_loader.get_valid_credential()은 저장된 토큰이 없으면
   oauth_service.authenticate()를 부르고, 그것은 InstalledAppFlow.
   run_local_server()로 브라우저를 연다. Qt 데스크톱 앱에서는 사용자가
   그 앞에 앉아 있으니 맞는 동작이었다. 여기서는 FastAPI 서버다 -
   업로드 요청 하나가 서버에서 브라우저를 띄우고 아무도 동의하지 않아
   영원히 멈춘다.

   그래서 oauth_manager.check_health()(로컬 토큰 파일만 읽는다. 네트워크도
   브라우저도 없다)로 먼저 막는다. 로그인이 없으면 그 사실을 그대로
   돌려주고 끝낸다. 만료된 토큰은 통과시킨다 - 갱신에는 브라우저가
   필요 없다. Sprint90이 verify_now()에서 get_valid_credential()을
   피한 것과 같은 판단이다.

Client Secret/Token 저장 경로/Account ID는 하드코딩하지 않는다 -
환경 변수로 설정 가능하고, credentials/ 아래의 합리적 기본값만 준다.
없는 client_secret을 대신 만들어 주지 않는다 - 경로를 그대로 적어
돌려준다.
"""

import json
import os
from typing import Optional

from app import config
from app.providers.upload.credential_loader import get_valid_credential
from app.providers.upload.file_token_store import FileTokenStore
from app.providers.upload.google_oauth_service import GoogleOAuthService
from app.providers.upload.youtube_upload_provider import YouTubeUploadProvider
from app.services import oauth_health, thumbnail_size_optimizer
from app.services.oauth_manager import OAuthManager
from app.services.real_youtube_runtime import DISABLED_MESSAGE
from app.services.studio_service import MEDIA_KINDS

_DEFAULT_CLIENT_SECRET_PATH = "credentials/client_secret.json"
_DEFAULT_TOKEN_STORE_PATH = "credentials/youtube_oauth_tokens.json"
_DEFAULT_ACCOUNT_ID = "default"

RESULT_FILENAME = "youtube_upload_result.json"

# 갱신만으로 해결되는 상태. 나머지는 사람이 브라우저에서 다시
# 로그인해야 하고, 그것은 서버가 대신 할 수 있는 일이 아니다.
_UPLOADABLE_HEALTH = (oauth_health.READY, oauth_health.EXPIRED)


def _load_publish_package(project_path: str) -> Optional[dict]:
    # Metadata Intelligence가 이미 계산해 저장해 둔 publish_package.json을
    # 읽는다 - 새로 계산하지 않는다(중복 생성 금지). 파일이 없으면 None -
    # 아래에서 기존 data dict 경로로 폴백한다. 손상된 파일도 같은 방식으로
    # 처리한다 - Metadata는 부가 산출물이므로 업로드 자체를 막지 않는다.
    #
    # 이 저장소에는 아직 publish_package.json을 만드는 단계가 없다.
    # 읽는 쪽 계약은 원본 그대로 둔다 - 그 단계가 이식되면 그날 바로
    # 맞물린다.
    path = os.path.join(project_path, "publish_package.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _build_metadata(
    topic: str, data: dict, project_path: str,
    thumbnail_path: Optional[str] = None,
) -> dict:
    # publish_package.json(단일 Source of Truth)이 있으면 그 값을 쓰고,
    # 없으면 원본 script data만 본다. data dict는 여기서도 호출자에서도
    # 절대 mutate하지 않는다.
    publish_package = _load_publish_package(project_path)

    if publish_package is not None:
        metadata = {
            "title": publish_package.get("title") or data.get("title") or topic,
            "description": (
                publish_package.get("description") or data.get("script") or ""
            ),
            "hashtags": (
                publish_package.get("tags")
                or publish_package.get("hashtags")
                or []
            ),
        }
        for package_key, metadata_key in (
            ("category_id", "category_id"),
            ("language", "language"),
            ("privacy_status", "privacy_status"),
            ("playlist_title", "playlist_title"),
        ):
            if publish_package.get(package_key):
                metadata[metadata_key] = publish_package[package_key]
    else:
        metadata = {
            "title": data.get("title") or topic,
            "description": data.get("script") or "",
            "hashtags": data.get("hashtags") or [],
        }

    if thumbnail_path is not None:
        metadata["thumbnail_path"] = thumbnail_path

    return metadata


def _resolve_video_path(project_path: str) -> str:
    return os.path.join(project_path, *MEDIA_KINDS["video"].split("/"))


def _resolve_thumbnail_path(project_path: str) -> Optional[str]:
    # step06이 만드는 썸네일을 실제로 찾아 YouTubeUploadProvider._upload_
    # thumbnail()에 넘길 수 있게 한다. 파일이 없으면(생성 실패/스킵) None -
    # 영상 업로드 자체는 막지 않는다.
    #
    # 2MB(YouTube API 한도)를 넘으면 optimize_thumbnail_for_upload()가
    # sibling 최적화 파일 경로를 대신 돌려준다. 원본 썸네일은 손대지
    # 않는다 - 시각 검수용으로 남는다.
    path = os.path.join(project_path, *MEDIA_KINDS["thumbnail"].split("/"))
    if not os.path.exists(path):
        return None

    return thumbnail_size_optimizer.optimize_thumbnail_for_upload(path)


def _check_health(client_secret_path: str, token_store_path: str,
                  account_id: str):
    """로컬 토큰 파일만 읽는다. 네트워크도 브라우저도 없다."""

    manager = OAuthManager(
        oauth_service=GoogleOAuthService(client_secret_path=client_secret_path),
        token_store=FileTokenStore(storage_path=token_store_path),
        account_id=account_id,
    )
    return manager.check_health()


def _refused(project_path: str, message: str) -> dict:
    """거절도 기록한다. 조용히 아무 일도 없었던 것처럼 두지 않는다."""

    return _record(project_path, {
        "success": False,
        "upload_id": None,
        "url": None,
        "error": message,
        "thumbnail_error": None,
        "playlist_error": None,
    })


def _record(project_path: str, payload: dict) -> dict:
    with open(
        os.path.join(project_path, RESULT_FILENAME), "w", encoding="utf-8",
    ) as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def run_youtube_upload_step(
    topic: str,
    project_path: str,
    data: dict,
) -> dict:
    if not config.ENABLE_YOUTUBE_UPLOAD:
        return _refused(project_path, DISABLED_MESSAGE)

    client_secret_path = os.environ.get(
        "YOUTUBE_OAUTH_CLIENT_SECRET_PATH", _DEFAULT_CLIENT_SECRET_PATH,
    )
    token_store_path = os.environ.get(
        "YOUTUBE_OAUTH_TOKEN_STORE_PATH", _DEFAULT_TOKEN_STORE_PATH,
    )
    account_id = os.environ.get("YOUTUBE_OAUTH_ACCOUNT_ID", _DEFAULT_ACCOUNT_ID)

    # 없는 것을 대신 만들지 않는다. 어디를 봤는지 그대로 적어 준다.
    if not os.path.exists(client_secret_path):
        return _refused(
            project_path,
            f"client_secret 파일이 없습니다: {client_secret_path}. "
            "Google Cloud Console에서 OAuth Client(Desktop)를 발급해 "
            "이 경로에 두거나 YOUTUBE_OAUTH_CLIENT_SECRET_PATH로 "
            "위치를 지정하십시오.",
        )

    health = _check_health(client_secret_path, token_store_path, account_id)

    if health.status not in _UPLOADABLE_HEALTH:
        return _refused(
            project_path,
            f"YouTube 로그인이 필요합니다({health.status}): {health.message} "
            "Studio의 YouTube 연결에서 Google 로그인을 먼저 완료하십시오.",
        )

    oauth_service = GoogleOAuthService(client_secret_path=client_secret_path)
    token_store = FileTokenStore(storage_path=token_store_path)
    credential = get_valid_credential(oauth_service, token_store, account_id)

    provider = YouTubeUploadProvider(credential=credential)
    video_path = _resolve_video_path(project_path)
    thumbnail_path = _resolve_thumbnail_path(project_path)
    metadata = _build_metadata(
        topic, data, project_path, thumbnail_path=thumbnail_path,
    )

    result = provider.upload(video_path, metadata)

    return _record(project_path, {
        "success": result.success,
        "upload_id": result.upload_id,
        "url": result.url,
        "error": result.error,
        "thumbnail_error": result.thumbnail_error,
        "playlist_error": result.playlist_error,
    })
