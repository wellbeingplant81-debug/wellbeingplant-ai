"""
Sprint237 - TikTok 에 올리는 걸음 (Publish Automation, Phase 5).

instagram_upload_step_service 의 세 번째 형제다. 같은 자리, 같은
판정 순서, 같은 결과 모양(success/outcome/upload_id/url/error) -
나중에 읽는 쪽이 플랫폼마다 다른 모양을 배우지 않아도 되게.

Instagram 과 무엇이 다른가
--------------------------
    Instagram  공개 URL 이 필요하다 -> AssetPublisher 를 넘긴다
    TikTok     FILE_UPLOAD 다 -> 넘기지 않는다(저장소가 필요 없다)

그 차이는 RuntimeCapabilities.requires_public_url 에 이미 적혀 있고
Adapter 가 그것을 보고 갈린다. 여기서 다시 판단하지 않는다.

판정 순서가 곧 안전장치다
-------------------------
앱 자격증명이 먼저고 로그인이 그다음이다. 앞 관문에서 막히면 뒤쪽
코드는 아예 실행되지 않는다 - 특히 브라우저를 여는 login() 까지 가지
않는다. Instagram 이 그렇게 하고, 그 순서를 그대로 따른다.

아직 못 하는 것
---------------
TikTok 앱이 없다. 심사를 통과하지 않은 앱은 비공개로만 올라간다.
그래서 여기서 하는 일은 대부분 "왜 안 되는지 사람이 읽을 수 있게
적는 것" 이다 - 조용히 아무 일도 안 하고 성공했다고 말하지 않는다.
"""

import json
import os
from typing import Optional

UPLOADED = "uploaded"
FAILED = "failed"
SKIPPED = "skipped"

RESULT_FILENAME = "tiktok_upload_result.json"

UNSET_MESSAGE = (
    "TikTok 앱 자격증명이 없습니다. TIKTOK_CLIENT_KEY 와 "
    "TIKTOK_CLIENT_SECRET 을 설정하십시오 - TikTok for Developers 에서 "
    "발급한 값입니다."
)


def _client_key() -> str:
    return os.environ.get("TIKTOK_CLIENT_KEY", "")


def _client_secret() -> str:
    return os.environ.get("TIKTOK_CLIENT_SECRET", "")


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def build_plan(topic: str, project_path: str, data: dict):
    """
    publish_package.json 이 있으면 그것을 쓴다 - 제목/설명/태그를
    여기서 다시 짓지 않는다(instagram 쪽과 같은 규칙이다).
    """

    from app.services.publishing.publishing_plan_model import PublishingPlan

    package = _load(os.path.join(project_path, "publish_package.json")) or {}
    data = data or {}

    return PublishingPlan(
        job_id=os.path.basename(project_path.rstrip("\\/")) or "tiktok",
        platform="tiktok",
        title=package.get("title") or data.get("title") or topic,
        description=(
            package.get("description") or data.get("script") or ""
        ),
        hashtags=(
            package.get("tags") or package.get("hashtags")
            or data.get("hashtags") or []
        ),
        output_folder=project_path,
    )


def _record(project_path: str, payload: dict) -> dict:
    with open(
        os.path.join(project_path, RESULT_FILENAME), "w", encoding="utf-8",
    ) as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def _refused(project_path: str, message: str) -> dict:
    return _record(project_path, {
        "success": False,
        "outcome": SKIPPED,
        "upload_id": None,
        "url": None,
        "error": message,
        # 바깥에서 할 일이 남았다는 뜻이다. 다시 눌러도 같은 자리에서
        # 같은 이유로 멈춘다.
        "retryable": False,
    })


def _from_connector_result(result) -> dict:
    published = result.status == "Published"

    return {
        "success": published,
        "outcome": UPLOADED if published else FAILED,
        "upload_id": result.external_id or None,
        # TikTok 은 올린 것의 공개 주소를 주지 않는다. 지어내지 않는다.
        "url": result.permalink or None,
        "error": result.message or None,
        "error_category": result.error_category or "",
        "retryable": result.retryable,
    }


def run_tiktok_upload_step(
    topic: str,
    project_path: str,
    data: dict,
    adapter=None,
) -> dict:
    if not (_client_key() and _client_secret()):
        return _refused(project_path, UNSET_MESSAGE)

    # 여기서만 무거운 것을 들인다. 자격증명이 없으면 Adapter 도
    # Runtime 도 import 되지 않는다.
    from app.services.publishing.runtime_backed_publish_adapter import (
        RuntimeBackedPublishAdapter,
    )
    from app.services.real_tiktok_runtime import build_default_tiktok_runtime

    if adapter is None:
        adapter = RuntimeBackedPublishAdapter(
            platform="tiktok",
            runtime=build_default_tiktok_runtime(),
            # FILE_UPLOAD 라 저장소가 필요 없다.
            asset_publisher=None,
        )

    result = adapter.submit(build_plan(topic, project_path, data))

    return _record(project_path, _from_connector_result(result))


def read_result(project_path: str) -> Optional[dict]:
    return _load(os.path.join(project_path, RESULT_FILENAME))
