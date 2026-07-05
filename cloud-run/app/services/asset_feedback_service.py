import json
import os
from datetime import datetime, timezone

from app.utils.atomic_write import atomic_write_json

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))

DEFAULT_FEEDBACK_PATH = os.path.join(_APP_ROOT, ".cache", "feedback.json")


def _load_records(feedback_path: str) -> list:

    if not os.path.exists(feedback_path):
        return []

    try:
        with open(feedback_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # 손상된 feedback 파일은 빈 이력으로 취급한다 - Learning Layer는
        # optional overlay이므로 여기서 예외를 전파하지 않는다.
        return []


def record(
    scene_id,
    provider: str,
    asset_type: str,
    selected_asset: str,
    outcome: str,
    feedback_path: str = DEFAULT_FEEDBACK_PATH,
) -> dict:
    """
    asset 선택 결과 하나를 feedback 이력에 append합니다.

    outcome은 "success"(스톡 provider가 채택됨) 또는 "fallback"
    (AI Image로 대체됨)입니다. 프로젝트 전역에 걸쳐 누적되는 공유
    이력이며(asset_cache.py의 .cache/assets/와 동일한 위치 규칙),
    시간이 지날수록 provider 학습에 사용됩니다.
    """

    records = _load_records(feedback_path)

    entry = {
        "scene_id": scene_id,
        "provider": provider,
        "asset_type": asset_type,
        "selected_asset": selected_asset,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    records.append(entry)

    atomic_write_json(feedback_path, records)

    return entry


def load_all(feedback_path: str = DEFAULT_FEEDBACK_PATH) -> list:
    """저장된 전체 feedback 이력을 반환합니다."""

    return _load_records(feedback_path)
