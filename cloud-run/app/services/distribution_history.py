"""
Sprint105 - Distribution Workflow Intelligence.

발행 시도 전체 이력을 append-only로 기록하는 별도 파일
(distribution_history.json). asset_feedback_service.py와 동일한
컨벤션(경로 파라미터 오버라이드, atomic_write_json, 파일 없음/손상 시
빈 리스트)을 그대로 따른다.

queue.json의 publish_result(distribution_store.py 소관, "최신 시도
결과 스냅샷")와 역할이 분리된다 - 이 모듈은 재시도해도 이전 기록을
덮어쓰지 않고 계속 쌓는다. 필드명은 §8-2 결정에 따라 "failure_reason"
대신 기존과 동일한 "error"를 쓴다.
"""

import json
import os
from datetime import datetime, timezone

from app.utils.atomic_write import atomic_write_json

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))

DEFAULT_HISTORY_PATH = os.path.join(_APP_ROOT, "output", "distribution_history.json")


def _load_records(history_path: str) -> list:

    if not os.path.exists(history_path):
        return []

    try:
        with open(history_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def record(
    video_id: str,
    platform: str,
    success: bool,
    platform_post_id: str,
    error: str,
    retry_count: int,
    history_path: str = DEFAULT_HISTORY_PATH,
) -> dict:
    """
    발행 시도 하나를 이력에 append한다. 같은 video_id/platform이라도
    호출할 때마다 새 레코드가 쌓인다(덮어쓰지 않음).
    """

    records = _load_records(history_path)

    entry = {
        "video_id": video_id,
        "platform": platform,
        "success": success,
        "platform_post_id": platform_post_id,
        "error": error,
        "retry_count": retry_count,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }

    records.append(entry)

    atomic_write_json(history_path, records)

    return entry


def load_all(video_id: str = None, history_path: str = DEFAULT_HISTORY_PATH) -> list:
    """저장된 발행 이력을 반환한다. video_id를 주면 그 항목만 필터링한다."""

    records = _load_records(history_path)

    if video_id is not None:
        records = [r for r in records if r["video_id"] == video_id]

    return records
