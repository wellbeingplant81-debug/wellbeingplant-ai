"""
Sprint104 - Video Distribution Intelligence.

Upload Queue를 JSON 파일 하나(video_id를 key로 하는 dict)에 영속화하는
계층. asset_feedback_service.py와 동일한 컨벤션을 따른다 - 경로
파라미터로 테스트 시 tmp 경로를 오버라이드할 수 있고, atomic_write_json
으로 저장하며, 파일이 없거나 손상돼도 예외 없이 빈 상태로 취급한다.

상태 전이 규칙(어떤 (status, action)이 허용되는지)은 이 모듈이 판단하지
않는다 - distribution_queue.transition()에 전부 위임하고, 이 모듈은
"그 결과를 실제로 어떻게 디스크에 반영하는지"만 책임진다.
"""

import json
import os
from datetime import datetime, timezone

from app.services import distribution_queue as dq
from app.utils.atomic_write import atomic_write_json

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))

DEFAULT_QUEUE_PATH = os.path.join(_APP_ROOT, "output", "distribution_queue.json")


class EntryNotFoundError(Exception):
    pass


class FieldEditNotAllowedError(Exception):
    pass


def _load_queue(queue_path: str) -> dict:

    if not os.path.exists(queue_path):
        return {}

    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_queue(queue: dict, queue_path: str) -> None:
    atomic_write_json(queue_path, queue)


def create_entry(
    video_id: str,
    output_path: str,
    title: str,
    description: str,
    hashtags: list,
    thumbnail_path: str,
    target_platforms: list,
    publish_mode: str = "immediate",
    scheduled_at: str = None,
    queue_path: str = DEFAULT_QUEUE_PATH,
) -> dict:
    """
    Upload Queue 항목을 새로 만든다. 상태는 generated로 시작해 같은
    호출 안에서 곧바로 waiting_review로 전이된 뒤 저장된다(SPEC:
    "explicit API -> generated -> waiting_review, 즉시 같은 호출
    내에서"). 자동 enqueue 훅은 없다 - 이 함수가 유일한 큐 생성
    경로이고, 반드시 명시적으로 호출돼야 한다.
    """

    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "video_id": video_id,
        "output_path": output_path,
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "thumbnail_path": thumbnail_path,
        "target_platforms": target_platforms,
        "publish_mode": publish_mode,
        "scheduled_at": scheduled_at,
        "status": dq.STATUS_GENERATED,
        "created_at": now,
        "updated_at": now,
        "publish_result": None,
    }

    entry["status"] = dq.transition(entry["status"], dq.ACTION_SUBMIT_FOR_REVIEW)

    queue = _load_queue(queue_path)
    queue[video_id] = entry
    _save_queue(queue, queue_path)

    return entry


def get_entry(video_id: str, queue_path: str = DEFAULT_QUEUE_PATH) -> dict:
    return _load_queue(queue_path).get(video_id)


def list_entries(status: str = None, queue_path: str = DEFAULT_QUEUE_PATH) -> list:

    entries = list(_load_queue(queue_path).values())

    if status is not None:
        entries = [entry for entry in entries if entry["status"] == status]

    return entries


def apply_action(
    video_id: str,
    action: str,
    field_overrides: dict = None,
    publish_result: dict = None,
    queue_path: str = DEFAULT_QUEUE_PATH,
) -> dict:
    """
    큐 항목 하나에 상태 전이 action을 적용한다. 전이 자체는
    distribution_queue.transition()이 판정하며(허용되지 않은 조합이면
    InvalidTransitionError가 그대로 전파된다 - 저장된 상태는 바뀌지
    않는다), 이 함수는 결과를 로드/검증/저장하는 책임만 진다.

    field_overrides(title/description/hashtags 등 사용자 콘텐츠)는
    전이 "전" 상태가 can_edit_fields()를 통과할 때만 허용된다(§8-3 -
    approved 이후 직접 수정 금지, cancel로 waiting_review까지 돌아가야
    다시 편집 가능).

    publish_result는 시스템이 발행 결과를 기록하는 필드라
    can_edit_fields() 제한과 무관하게 항상 설정 가능하다(publishing
    상태에서 mark_published/mark_failed로 전이할 때 씀).
    """

    queue = _load_queue(queue_path)
    entry = queue.get(video_id)

    if entry is None:
        raise EntryNotFoundError(video_id)

    previous_status = entry["status"]
    new_status = dq.transition(previous_status, action)

    if field_overrides:
        if not dq.can_edit_fields(previous_status):
            raise FieldEditNotAllowedError(
                f"Cannot edit fields while status is '{previous_status}'"
            )
        entry.update(field_overrides)

    if publish_result is not None:
        entry["publish_result"] = publish_result

    entry["status"] = new_status
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()

    queue[video_id] = entry
    _save_queue(queue, queue_path)

    return entry
