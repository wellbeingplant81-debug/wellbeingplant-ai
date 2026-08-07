"""
Sprint84 - Production Workflow.

상태를 저장하지 않고 산출물에서 유도한다. 사람이 내린 결정(승인)만
저장한다.

유도하는 이유가 있다. 상태를 파일에 굳혀 두면 그 순간의 사실이 박제된다 -
"Inspection"으로 적어 둔 프로젝트를 나중에 재생성해서 scene이 실패해도
파일은 여전히 Inspection이라고 말한다. Sprint80에서 파이프라인 진행을
로그가 아니라 산출물로 판정한 것과 같은 이유다. script.json이 있으면
대본이 끝난 것이고, 실패한 scene이 있으면 재생성이 필요한 것이다.

승인은 다르다. 파일에서 유도할 수 없는 사람의 판단이므로 저장해야
하고, 새로고침을 넘어 살아남아야 한다.

저장 위치는 프로젝트 디렉터리 밖이다. 생산 산출물은 한 바이트도 손대지
않는다.

여기서는 엔진을 부르지 않는다. 승인은 workflow 상태만 바꾸며 이미지,
영상, 평가는 그대로다.
"""

import json
import os
import re
from datetime import datetime, timezone


DRAFT = "draft"
GENERATING = "generating"
INSPECTION = "inspection"
NEEDS_REGENERATION = "needs_regeneration"
# Sprint148 - 사람이 "올리겠다"고 한 것. 유도할 수 없는 결정이므로
# 저장한다 - 승인과 같은 부류다.
WAITING_APPROVAL = "waiting_approval"
APPROVED = "approved"
# Sprint148 - 지금 올리고 있다. 저장하지 않는다 - 도는 작업이 곧
# 사실이므로 그것에서 유도한다.
UPLOADING = "uploading"
UPLOAD_FAILED = "upload_failed"
PUBLISHED = "published"

STATUSES = (
    DRAFT, GENERATING, INSPECTION, NEEDS_REGENERATION, WAITING_APPROVAL,
    APPROVED, UPLOADING, UPLOAD_FAILED, PUBLISHED,
)

LABELS = {
    DRAFT: "Draft",
    GENERATING: "Generating",
    INSPECTION: "Ready",
    NEEDS_REGENERATION: "Needs Regeneration",
    WAITING_APPROVAL: "Waiting Approval",
    APPROVED: "Approved",
    UPLOADING: "Uploading",
    UPLOAD_FAILED: "Failed",
    PUBLISHED: "Done",
}

# 사람이 내린 결정만 저장한다. 나머지는 유도한다.
#
# Sprint92 - PUBLISHED는 저장하지 않는다. 업로드가 남긴 산출물
# (youtube_upload_result.json)에서 유도한다 - script.json이 있으면
# 대본이 끝난 것이라고 판정하는 것과 같은 방식이다. 사람이 내린 결정은
# 승인 하나뿐이고, 업로드 성공은 사실이지 판단이 아니다.
STORED_STATUSES = (WAITING_APPROVAL, APPROVED)

STORE_FILENAME = "workflow.json"

# Sprint91의 youtube_upload_step_service가 남기는 파일.
#
# 이름을 여기에 다시 적었다. import해 오는 편이 낫지만, 그러면 이
# 모듈이 Upload Core와 OAuth 전체를 끌고 들어온다 - workflow는 산출물을
# 읽기만 하는 순수 계층이고 그 사실을 지키는 테스트가 있다. 대신 두
# 이름이 어긋나면 걸리도록 테스트로 묶어 두었다.
_UPLOAD_RESULT_FILENAME = "youtube_upload_result.json"
_UPLOADED = "uploaded"
_FAILED = "failed"

_TIMESTAMP = re.compile(r"^(\d{8})_(\d{6})")


def _valid_id(project_id: str) -> str:
    """저장소 키로 쓸 수 있는 이름인지. 경로 구분자가 섞이면 거부한다 -
    Sprint65의 resolve_project_path와 같은 원칙이다."""

    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id가 비어 있습니다.")

    candidate = project_id.strip()

    if candidate in (".", "..") or os.path.basename(candidate) != candidate:
        raise ValueError(f"project_id가 올바르지 않습니다: {project_id!r}")

    return candidate


def _load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_store(store_path: str) -> dict:
    """저장된 결정들. 깨져 있으면 빈 것으로 읽는다 - 승인 기록 하나가
    망가졌다고 큐 전체가 죽을 이유는 없다."""

    stored = _load(store_path)

    return stored if isinstance(stored, dict) else {}


def _save_store(store_path: str, stored: dict) -> None:
    directory = os.path.dirname(store_path)

    if directory:
        os.makedirs(directory, exist_ok=True)

    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(store_path, stored)


def approve(project_id: str, store_path: str) -> dict:
    """
    승인한다. workflow 상태만 바뀐다 - 이미지도 영상도 평가도 그대로다.

    이미 승인된 것을 다시 승인해도 처음 시각을 유지한다. 언제 판단했는지가
    기록의 요점인데 다시 누를 때마다 갱신되면 그것이 사라진다.
    """

    key = _valid_id(project_id)
    stored = load_store(store_path)

    if stored.get(key, {}).get("status") != APPROVED:
        stored[key] = {
            "status": APPROVED,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_store(store_path, stored)

    return stored[key]


def request_upload(project_id: str, store_path: str) -> dict:
    """
    사람이 올리겠다고 한다. 올리지는 않는다.

    승인과 같은 부류의 결정이라 저장한다 - 파일에서 유도할 수 없고,
    새로고침을 넘어 살아남아야 한다.

    이미 승인된 것은 되돌리지 않는다. 요청은 승인 앞의 단계이므로
    뒤로 끌어내리면 사람이 내린 판단을 지우는 것이 된다.
    """

    key = _valid_id(project_id)
    stored = load_store(store_path)
    current = stored.get(key, {})

    if current.get("status") == APPROVED:
        return current

    if current.get("status") != WAITING_APPROVAL:
        stored[key] = {
            "status": WAITING_APPROVAL,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_store(store_path, stored)

    return stored[key]


def reject(project_id: str, store_path: str, reason: str = "") -> dict:
    """
    거절한다. 요청을 거두고 사유를 남긴다.

    사유는 사람이 쓴 것이므로 저장한다. 상태는 저장하지 않는다 -
    거절하면 요청 이전으로 돌아가고, 그때의 상태는 산출물이 말한다.
    """

    key = _valid_id(project_id)
    stored = load_store(store_path)

    stored[key] = {
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "rejection_reason": (reason or "").strip(),
    }

    _save_store(store_path, stored)

    return stored[key]


def unapprove(project_id: str, store_path: str) -> None:
    """승인을 거둔다. 유도 상태로 돌아간다."""

    key = _valid_id(project_id)
    stored = load_store(store_path)

    if key in stored:
        del stored[key]
        _save_store(store_path, stored)


def _failed_scenes(project_path: str) -> list:
    report = _load(os.path.join(project_path, "quality_report.json"))

    if not report:
        return []

    evaluation = report.get("ai_quality_evaluation") or {}

    return [
        scene.get("scene")
        for scene in evaluation.get("scenes", [])
        if scene.get("regenerate")
    ]


def _upload_outcome(project_path: str):
    """업로드가 남긴 사실. 시도한 적이 없으면 None.

    건너뛴 것(outcome=skipped)은 아무 일도 없었던 것과 같게 다룬다 -
    플래그가 꺼져 있거나 아직 승인되지 않아서 안 올린 프로젝트가
    업로드 실패로 보이면 안 된다."""

    result = _load(os.path.join(project_path, _UPLOAD_RESULT_FILENAME))

    if not isinstance(result, dict):
        return None

    outcome = result.get("outcome")

    return outcome if outcome in (_UPLOADED, _FAILED) else None


def _upload_row(project_path: str):
    """화면이 보여줄 업로드 사실. 시도한 적이 없으면 None."""

    result = _load(os.path.join(project_path, _UPLOAD_RESULT_FILENAME))

    if not isinstance(result, dict):
        return None

    return {
        "outcome": result.get("outcome"),
        "url": result.get("url"),
        "error": result.get("error"),
        "thumbnail_error": result.get("thumbnail_error"),
        "playlist_error": result.get("playlist_error"),
    }


def status_for(project_path: str, stored: dict = None,
               running: bool = False, uploading: bool = False) -> str:
    """
    지금의 상태. 순수 읽기입니다.

    우선순위가 의미를 갖는다. 지금 돌고 있으면 그것이 가장 최신 사실이고,
    업로드 결과가 있으면 그것이 승인보다 나중의 사실이며, 사람이
    승인했으면 그것이 유도보다 우선한다.
    """

    # Sprint148 - 지금 올리고 있으면 그것이 가장 최신 사실이다.
    if uploading:
        return UPLOADING

    if running:
        return GENERATING

    # Sprint92 - 승인보다 뒤에 일어난 일이므로 승인보다 먼저 본다.
    outcome = _upload_outcome(project_path)

    if outcome == _UPLOADED:
        return PUBLISHED

    if outcome == _FAILED:
        return UPLOAD_FAILED

    decided = (stored or {}).get("status")

    if decided in STORED_STATUSES:
        return decided

    if not os.path.exists(os.path.join(project_path, "script.json")):
        return DRAFT

    if not os.path.exists(os.path.join(project_path, "quality_report.json")):
        # 대본은 있는데 평가가 없다 - 아직 만드는 중이거나 중간에 멈췄다.
        return GENERATING

    return NEEDS_REGENERATION if _failed_scenes(project_path) else INSPECTION


def _created_at(project_id: str):
    """프로젝트 이름이 곧 생성 시각이다. 형식이 다르면 None -
    파일 mtime으로 추측하지 않는다."""

    match = _TIMESTAMP.match(project_id or "")

    if not match:
        return None

    try:
        stamp = datetime.strptime(
            f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S",
        )
    except ValueError:
        return None

    return stamp.strftime("%Y-%m-%d %H:%M:%S")


def queue(root: str, store_path: str, running=None,
          uploading=None) -> list:
    """
    프로젝트 목록과 각각의 상태. 순수 읽기입니다.

    없는 값은 None으로 둔다. 0이나 빈 문자열을 넣으면 화면이 그것을
    값으로 읽는다 - "Unknown"이라고 쓰는 것은 화면의 일이다.
    """

    if not os.path.isdir(root):
        return []

    stored = load_store(store_path)
    running = set(running or ())
    uploading = set(uploading or ())

    rows = []

    for name in sorted(os.listdir(root), reverse=True):
        path = os.path.join(root, name)

        if not os.path.isdir(path):
            continue

        meta = _load(os.path.join(path, "project.json"))

        if meta is None:
            continue

        script = _load(os.path.join(path, "script.json")) or {}
        report = _load(os.path.join(path, "quality_report.json")) or {}

        evaluation = report.get("ai_quality_evaluation") or {}
        checks = (report.get("technical_validation") or {}).get("checks") or {}
        duration = (checks.get("video_duration") or {}).get("duration_seconds")

        failed = _failed_scenes(path)

        rows.append({
            "project_id": name,
            "topic": meta.get("topic"),
            "title": script.get("title"),
            "channel": meta.get("channel"),
            "created_at": _created_at(name),
            "duration": duration,
            "quality": (evaluation.get("scores") or {}).get("overall_quality"),
            "scene_count": len(script.get("scenes") or []),
            "failed_scenes": failed,
            "has_video": os.path.exists(
                os.path.join(path, "video", "final_short.mp4"),
            ),
            "status": status_for(
                path, stored.get(name), name in running,
                name in uploading,
            ),
            "approved_at": (stored.get(name) or {}).get("approved_at"),
            # Sprint148 - 사람이 내린 결정들. 유도할 수 없으므로 저장한
            # 것을 그대로 나른다.
            "requested_at": (stored.get(name) or {}).get("requested_at"),
            "rejected_at": (stored.get(name) or {}).get("rejected_at"),
            "rejection_reason": (
                (stored.get(name) or {}).get("rejection_reason")
            ),
            # Sprint92 - 업로드가 실패했으면 왜인지 화면이 그대로
            # 보여줄 수 있어야 한다. 시도한 적이 없으면 None이다.
            "upload": _upload_row(path),
        })

    return rows


def filter_rows(rows: list, status: str) -> list:
    """상태로 거른다. 모르는 값은 조용히 전체를 돌려주지 않고 거부한다."""

    if status in (None, "", "all"):
        return list(rows or [])

    if status not in STATUSES:
        raise ValueError(
            f"알 수 없는 상태입니다: {status!r}. "
            f"사용 가능한 값: {['all'] + list(STATUSES)}"
        )

    return [row for row in (rows or []) if row.get("status") == status]
