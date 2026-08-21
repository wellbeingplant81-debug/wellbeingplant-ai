"""
Sprint101 - Instagram Upload Step (Epic 53).

Sprint97(Runtime), Sprint99(Storage), Sprint100(Publish Adapter)를 엮어
프로젝트 하나를 Instagram Reels로 올린다.

이 파일에는 업로드 로직이 없다. 게시 순서(공개 URL 준비, Container
생성, 상태 폴링, Publish, 일시적 오류 재시도, Dry Run)는 전부
RuntimeBackedPublishAdapter가 이미 갖고 있다. 여기가 하는 일은 셋뿐이다.

  1. 올려도 되는지 판정한다 (플래그, Meta 자격증명, 로그인 상태)
  2. 프로젝트 산출물을 PublishingPlan으로 옮겨 담는다
  3. 결과를 파일로 남긴다

youtube_upload_step_service와 같은 모양으로 만들었지만 그 파일을
건드리지 않았다. 실제로 두 플랫폼이 다르게 동작하는 지점이 있다 -
YouTube는 로컬 파일 경로를 그대로 올리고, Instagram은 공개 URL만
받는다. 그 차이는 Adapter가 capabilities.requires_public_url로 이미
분기하고 있으므로 여기서 다시 판단하지 않는다.

공개 URL이 없으면(STORAGE_PROVIDER가 local이면 항상 그렇다) Adapter가
"공개 URL이 없습니다"라고 답한다. 여기서 미리 막지 않는 이유는, 그
판정이 이미 Adapter에 있고 메시지도 그쪽이 더 정확하기 때문이다 -
같은 판정을 두 곳에 두지 않는다.

브라우저 경계는 YouTube와 같다. Adapter가 부르는 runtime.login()은
저장된 토큰이 없으면 InstagramOAuthService.authenticate()로 이어지고
그것은 브라우저를 연다. 그래서 그 앞에서 check_health()(로컬 토큰
파일만 읽는다)로 막는다 - Sprint90/91에서 YouTube에 같은 함정이
있었다.
"""

import json
import os
from typing import Optional

from app import config
from app.providers.upload.instagram_oauth_service import InstagramOAuthService
from app.providers.upload.instagram_token_store import InstagramTokenStore
from app.services import oauth_health
from app.services.oauth_manager import OAuthManager
from app.services.studio_upload import FAILED, SKIPPED, UPLOADED

# Sprint256 - 자리가 아니라 이름만 안다.
#
# 예전에는 여기가 상대 경로였고 켠 자리(cwd)를 따라갔다. 로그인
# (instagram_oauth_manager)은 credential_paths 를 쓰는데 이쪽만 쓰지
# 않아서, 같은 계정인데 서로 다른 파일을 볼 수 있었다.
#
# YouTube 에서 그것이 실제로 일어났다 - Sprint254 의 업로드가 두 번
# invalid_scope 로 죽었고 원인은 저장소가 둘로 갈린 것이었다.
# Instagram 은 아직 자격증명이 없어 드러나지 않았을 뿐이다.
_TOKEN_STORE_FILENAME = "instagram_oauth_tokens.json"
_DEFAULT_REDIRECT_URI = "http://localhost:8551/callback"
_DEFAULT_ACCOUNT_ID = "default"

RESULT_FILENAME = "instagram_upload_result.json"

DISABLED_MESSAGE = "ENABLE_INSTAGRAM_UPLOAD가 꺼져 있습니다."

# 갱신만으로 해결되는 상태. 나머지는 사람이 브라우저에서 다시
# 로그인해야 하고, 그것은 서버가 대신 할 수 있는 일이 아니다.
_UPLOADABLE_HEALTH = (oauth_health.READY, oauth_health.EXPIRED)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _client_id() -> str:
    return _env("INSTAGRAM_OAUTH_CLIENT_ID")


def _client_secret() -> str:
    return _env("INSTAGRAM_OAUTH_CLIENT_SECRET")


def _token_store_path() -> str:
    """로그인 결과를 읽고 쓰는 자리. 환경변수 > 저장소 > 사용자 자리."""

    from app.services import credential_paths

    return credential_paths.resolve(
        "INSTAGRAM_OAUTH_TOKEN_STORE_PATH", _TOKEN_STORE_FILENAME)


def _account_id() -> str:
    return _env("INSTAGRAM_OAUTH_ACCOUNT_ID", _DEFAULT_ACCOUNT_ID)


def _check_health():
    """로컬 토큰 파일만 읽는다. 네트워크도 브라우저도 없다."""

    manager = OAuthManager(
        oauth_service=InstagramOAuthService(
            client_id=_client_id(),
            client_secret=_client_secret(),
            redirect_uri=_env("INSTAGRAM_OAUTH_REDIRECT_URI", _DEFAULT_REDIRECT_URI),
        ),
        token_store=InstagramTokenStore(storage_path=_token_store_path()),
        account_id=_account_id(),
    )

    return manager.check_health()


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def build_plan(topic: str, project_path: str, data: dict):
    """
    프로젝트 산출물을 PublishingPlan으로 옮겨 담는다.

    Sprint93이 만든 publish_package.json이 있으면 그것을 쓴다 - 제목/
    설명/해시태그가 이미 정리돼 있고, YouTube 업로드가 읽는 것과 같은
    자리다. 없으면 script.json으로 폴백한다(YouTube 쪽과 같은 관례).

    캡션은 Adapter의 build_caption()이 만든다 - 여기서 문자열을 조립하지
    않는다.
    """

    from app.services.publishing.publishing_plan_model import PublishingPlan

    package = _load(os.path.join(project_path, "publish_package.json")) or {}

    title = package.get("title") or data.get("title") or topic
    description = package.get("description") or data.get("script") or ""
    hashtags = (
        package.get("hashtags")
        or package.get("tags")
        or data.get("hashtags")
        or []
    )

    return PublishingPlan(
        job_id=os.path.basename(os.path.normpath(project_path)),
        platform="Instagram",
        title=title,
        description=description,
        hashtags=list(hashtags),
        output_folder=project_path,
    )


def _record(project_path: str, payload: dict) -> dict:
    with open(
        os.path.join(project_path, RESULT_FILENAME), "w", encoding="utf-8",
    ) as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def _refused(project_path: str, message: str) -> dict:
    """거절도 기록한다. 조용히 아무 일도 없었던 것처럼 두지 않는다."""

    return _record(project_path, {
        "success": False,
        "outcome": SKIPPED,
        "upload_id": None,
        "url": None,
        "storage_url": None,
        "error": message,
        "error_category": "",
    })


def _from_connector_result(result) -> dict:
    """Adapter의 답을 결과 파일 모양으로 옮긴다.

    YouTube 결과와 같은 키를 쓴다(success/outcome/upload_id/url/error) -
    나중에 읽는 쪽이 플랫폼마다 다른 모양을 배우지 않아도 되게."""

    published = result.status == "Published"

    return {
        "success": published,
        "outcome": UPLOADED if published else FAILED,
        "upload_id": result.external_id or None,
        "url": result.permalink or None,
        "storage_url": result.storage_url or None,
        "error": result.message or None,
        "error_category": result.error_category or "",
        "retryable": result.retryable,
    }


def run_instagram_upload_step(
    topic: str,
    project_path: str,
    data: dict,
    adapter=None,
) -> dict:
    """
    승인된 프로젝트 하나를 Instagram Reels로 올린다.

    판정 순서가 곧 안전장치다. 플래그가 먼저고, Meta 자격증명이
    그다음이고, 로그인 상태가 그다음이다. 앞 관문에서 막히면 뒤쪽
    코드는 아예 실행되지 않는다 - 특히 브라우저를 여는 login()까지
    가지 않는다.
    """

    if not config.ENABLE_INSTAGRAM_UPLOAD:
        return _refused(project_path, DISABLED_MESSAGE)

    if not (_client_id() and _client_secret()):
        return _refused(
            project_path,
            "Meta App 자격증명이 없습니다. INSTAGRAM_OAUTH_CLIENT_ID와 "
            "INSTAGRAM_OAUTH_CLIENT_SECRET을 설정하십시오 - Meta "
            "Developer에서 발급한 값입니다.",
        )

    health = _check_health()

    if health.status not in _UPLOADABLE_HEALTH:
        return _refused(
            project_path,
            f"Instagram 로그인이 필요합니다({health.status}): {health.message}",
        )

    # 여기서만 무거운 것을 들인다. 플래그가 꺼져 있으면 Adapter도
    # Storage(boto3)도 import되지 않는다.
    from app.providers.storage import storage_factory
    from app.services.publishing.instagram_adapter import InstagramAdapter

    if adapter is None:
        adapter = InstagramAdapter(
            asset_publisher=storage_factory.build_asset_publisher(),
        )

    result = adapter.submit(build_plan(topic, project_path, data))

    return _record(project_path, _from_connector_result(result))


def read_result(project_path: str) -> Optional[dict]:
    """업로드 결과. 없으면 None - 아직 시도한 적이 없다는 뜻이다."""

    return _load(os.path.join(project_path, RESULT_FILENAME))
