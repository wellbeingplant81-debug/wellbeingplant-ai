"""
Sprint104 - Video Distribution Intelligence. Review Gate API.

이 리포의 기존 라우터 컨벤션(app/routers/factory.py)을 따르는 얇은
계층이다 - 상태 전이 판정은 distribution_queue, 저장은
distribution_store, 실제 발행 오케스트레이션은 distribution_service에
전부 위임하고, 이 파일은 HTTP 계약(요청 파싱/에러코드 변환)만
책임진다.

config.ENABLE_DISTRIBUTION=False(기본값)면 상태를 바꾸는 엔드포인트
(enqueue/approve/reject/re-review/cancel/publish)는 전부 403을
반환하고 하위 함수를 아예 호출하지 않는다 - 조회(GET) 엔드포인트는
플래그와 무관하게 항상 동작한다(부작용이 없고, 꺼져 있으면 큐가
비어 있을 뿐이다).

자동 enqueue 훅은 없다 - POST /distribution/queue가 유일한 큐 생성
경로이며, 기존 영상 생성 파이프라인(factory_service.py 등)은 이
라우터를 전혀 알지 못한다.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from app import config
from app.models.distribution_request import ApproveRequest, EnqueueRequest
from app.services import distribution_queue as dq
from app.services import distribution_service
from app.services import distribution_store

router = APIRouter()


def _require_enabled():
    if not config.ENABLE_DISTRIBUTION:
        raise HTTPException(
            status_code=403,
            detail="Distribution is disabled (ENABLE_DISTRIBUTION=False)",
        )


def _apply_action_or_error(video_id: str, action: str, **kwargs) -> dict:
    try:
        return distribution_store.apply_action(video_id, action, **kwargs)
    except distribution_store.EntryNotFoundError:
        raise HTTPException(status_code=404, detail=f"No queue entry for video_id={video_id}")
    except distribution_store.FieldEditNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except dq.InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/distribution/queue")
def enqueue(request: EnqueueRequest):

    _require_enabled()

    return distribution_store.create_entry(
        video_id=request.video_id,
        output_path=request.output_path,
        title=request.title,
        description=request.description,
        hashtags=request.hashtags,
        thumbnail_path=request.thumbnail_path,
        target_platforms=request.target_platforms,
        publish_mode=request.publish_mode,
        scheduled_at=request.scheduled_at,
    )


@router.get("/distribution/queue")
def list_queue(status: Optional[str] = None):
    return distribution_store.list_entries(status=status)


@router.get("/distribution/queue/{video_id}")
def get_queue_item(video_id: str):

    entry = distribution_store.get_entry(video_id)

    if entry is None:
        raise HTTPException(status_code=404, detail=f"No queue entry for video_id={video_id}")

    return entry


@router.post("/distribution/queue/{video_id}/approve")
def approve(video_id: str, request: ApproveRequest):

    _require_enabled()

    field_overrides = request.model_dump(exclude_none=True)

    return _apply_action_or_error(
        video_id, dq.ACTION_APPROVE, field_overrides=field_overrides,
    )


@router.post("/distribution/queue/{video_id}/reject")
def reject(video_id: str):

    _require_enabled()

    return _apply_action_or_error(video_id, dq.ACTION_REJECT)


@router.post("/distribution/queue/{video_id}/re-review")
def re_review(video_id: str):

    _require_enabled()

    return _apply_action_or_error(video_id, dq.ACTION_RE_REVIEW)


@router.post("/distribution/queue/{video_id}/cancel")
def cancel(video_id: str):

    _require_enabled()

    return _apply_action_or_error(video_id, dq.ACTION_CANCEL)


@router.post("/distribution/queue/{video_id}/publish")
def publish(video_id: str):

    _require_enabled()

    try:
        return distribution_service.publish(video_id)
    except distribution_store.EntryNotFoundError:
        raise HTTPException(status_code=404, detail=f"No queue entry for video_id={video_id}")
    except dq.InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
