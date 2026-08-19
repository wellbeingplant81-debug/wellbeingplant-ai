"""
Sprint235 - 올릴 것을 줄 세운다 (Publish Automation, Phase 1).

이 파일이 하는 일은 하나다 - **무엇을 어디에 올릴 차례인지 기억한다.**
올리지 않는다. 자격증명도 모르고, 바깥도 부르지 않는다.

왜 여기까지만 하는가
--------------------
올리는 일은 이미 있는 것들이 한다.

    누구인가        social_accounts · OAuthManager · FileTokenStore
    어떻게 올리나   PublishingRuntimeProtocol 구현체들
    무엇을 올리나   publish_package.json
    공개 URL       AssetPublisher

여기서 그것들을 부르기 시작하면 같은 일을 두 곳이 하게 되고, 어느 날
한쪽만 고쳐진다 - 이 저장소가 여러 번 겪은 그것이다. 그래서 줄은
줄만 안다.

DB 를 만들지 않는다
-------------------
이 프로그램에는 DB 가 하나도 없다. 사람의 결정 하나를 적는 자리는
이미 정해져 있다 - %APPDATA%\\AI영상제작소\\ 아래의 json 한 장이고,
free_workspace 와 studio_upload 가 그렇게 산다. 줄 세우기 때문에
SQLite 를 들이면 이 집에 없던 것이 생기고, 백업·잠금·마이그레이션이
따라온다.

파일 하나로 충분한가
--------------------
줄에 서는 것은 사람이 만든 영상이다. 하루에 몇 개다. 수천 개가 아니고
여러 컴퓨터가 같은 줄을 보지도 않는다. 그 크기에는 json 한 장이 맞다.

껐다 켜는 것을 먼저 생각한다
----------------------------
UPLOADING 인 채로 컴퓨터가 꺼지면 그 줄은 영영 그 상태로 남는다.
아무도 집지 않고, 사람은 올라가는 중인 줄 안다. 그래서 recover_stuck 이
있다 - 켤 때 한 번 불러 끊긴 것을 다시 세운다.
"""

import json
import os
import uuid
from datetime import datetime, timezone

VERSION = 1

STORE_FILENAME = "publish_queue.json"

PENDING = "PENDING"
UPLOADING = "UPLOADING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"

STATES = (PENDING, UPLOADING, SUCCESS, FAILED)

# 아직 끝나지 않은 것들. 여기 있는 동안에는 같은 것을 또 세우지 않는다.
LIVE = (PENDING, UPLOADING)

# 올릴 수 있는 곳. social_accounts.PLATFORMS 와 같은 이름을 쓴다 -
# 여기서 새 이름을 짓지 않는다. 다만 import 하지 않는다: 줄이
# 자격증명 계층을 끌고 들어오면 그것이 없는 자리에서 줄도 못 읽는다.
PLATFORMS = ("youtube", "instagram", "tiktok")

# 끊긴 줄을 다시 세울 때 남기는 말. 사람이 나중에 왜 다시 섰는지
# 알아야 한다.
INTERRUPTED = "올리는 중에 프로그램이 끊겼습니다. 다시 줄에 세웠습니다."


def default_store_path() -> str:
    """
    줄이 사는 곳. 프로젝트 폴더 밖이다 - 줄은 프로젝트 하나의 것이
    아니라 이 사람의 것이다.
    """

    from app import runtime_paths

    return os.path.join(runtime_paths.home(), STORE_FILENAME)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read(store_path: str) -> dict:
    """
    깨져 있으면 없는 것으로 읽는다. 기억 하나가 망가졌다고 화면
    전체가 죽을 이유는 없다 - free_workspace 가 이미 그렇게 한다.
    """

    try:
        with open(store_path, encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        return {"version": VERSION, "items": []}

    if not isinstance(found, dict) or not isinstance(found.get("items"), list):
        return {"version": VERSION, "items": []}

    rows = [row for row in found["items"]
            if isinstance(row, dict) and row.get("id")
            and row.get("state") in STATES]

    return {"version": VERSION, "items": rows}


def _write(store_path: str, data: dict) -> None:
    folder = os.path.dirname(os.path.abspath(store_path))

    if folder:
        os.makedirs(folder, exist_ok=True)

    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(store_path, data)


def every(store_path: str) -> list:
    """선 순서 그대로. 넣은 차례가 곧 올릴 차례다."""

    return _read(store_path)["items"]


def find(store_path: str, item_id: str):
    for row in _read(store_path)["items"]:
        if row["id"] == item_id:
            return row

    return None


def next_pending(store_path: str):
    """
    다음에 집을 것. UPLOADING 은 건너뛴다 - 두 일꾼이 같은 것을 집으면
    같은 영상이 두 번 올라간다.
    """

    for row in _read(store_path)["items"]:
        if row["state"] == PENDING:
            return row

    return None


def claim(store_path: str):
    """
    다음 차례를 집어 그 자리에서 UPLOADING 으로 바꾼다.

    Sprint237 - next_pending 으로 보고 mark_uploading 으로 적으면 그
    사이가 열려 있다. 두 일꾼이 같은 것을 보고 같은 영상을 두 번
    올릴 수 있다. 한 번의 읽고-바꾸고-적기로 끝낸다 - 집는 것이 곧
    잠그는 것이다.

    집을 것이 없으면 None. 파일은 건드리지 않는다.
    """

    data = _read(store_path)

    for row in data["items"]:
        if row["state"] != PENDING:
            continue

        row["state"] = UPLOADING
        row["started_at"] = _now()
        row["attempts"] = int(row.get("attempts", 0)) + 1

        _write(store_path, data)

        return row

    return None


def add(store_path: str, project_id: str, platform: str, **rest) -> dict:
    """
    줄에 세운다. 아직 끝나지 않은 같은 줄이 있으면 그것을 돌려준다 -
    같은 영상을 같은 곳에 두 번 올리는 일이 실수로 일어나면 안 된다.
    """

    project_id = str(project_id or "").strip()
    platform = str(platform or "").strip().lower()

    if not project_id:
        raise ValueError("어느 프로젝트를 올릴지 정해야 합니다.")

    if platform not in PLATFORMS:
        # 받아 두면 나중에 조용히 아무 데도 안 올라간다. 사람은 줄에
        # 있는 것을 보고 올라갔다고 믿는다.
        raise ValueError(
            f"올릴 수 없는 곳입니다: {platform!r}. "
            f"쓸 수 있는 곳은 {', '.join(PLATFORMS)} 입니다.")

    data = _read(store_path)

    for row in data["items"]:
        if (row["project_id"] == project_id and row["platform"] == platform
                and row["state"] in LIVE):
            return row

    made = {
        "id": uuid.uuid4().hex[:12],
        "project_id": project_id,
        "platform": platform,
        "state": PENDING,
        "queued_at": _now(),
        "started_at": "",
        "finished_at": "",
        "attempts": 0,
        "reason": "",
        "retryable": False,
        "url": "",
    }

    made.update({k: v for k, v in rest.items() if k not in made})

    data["items"].append(made)
    _write(store_path, data)

    return made


def _change(store_path: str, item_id: str, apply) -> dict:
    data = _read(store_path)

    for row in data["items"]:
        if row["id"] == item_id:
            apply(row)
            _write(store_path, data)

            return row

    raise KeyError(f"그런 줄이 없습니다: {item_id!r}")


def mark_uploading(store_path: str, item_id: str) -> dict:
    def apply(row):
        if row["state"] == SUCCESS:
            # 올라간 것을 다시 올리지 않는다.
            raise ValueError("이미 올린 것입니다.")

        row["state"] = UPLOADING
        row["started_at"] = _now()
        row["attempts"] = int(row.get("attempts", 0)) + 1

    return _change(store_path, item_id, apply)


def mark_success(store_path: str, item_id: str, url: str = "") -> dict:
    def apply(row):
        row["state"] = SUCCESS
        row["finished_at"] = _now()
        row["url"] = str(url or "")
        row["reason"] = ""
        row["retryable"] = False

    return _change(store_path, item_id, apply)


def mark_failed(store_path: str, item_id: str, reason: str,
                retryable: bool = False) -> dict:
    """
    왜 죽었는지 남긴다. "실패"만 적으면 사람은 무엇을 고쳐야 할지
    모르고, 다시 눌러도 같은 자리에서 같은 이유로 죽는다.

    retryable 은 줄이 정하지 않는다 - 올리는 쪽이 안다
    (TransientRuntimeError 인가 NonRetryableRuntimeError 인가).
    """

    def apply(row):
        row["state"] = FAILED
        row["finished_at"] = _now()
        row["reason"] = str(reason or "")
        row["retryable"] = bool(retryable)

    return _change(store_path, item_id, apply)


def retry(store_path: str, item_id: str) -> dict:
    """
    다시 줄에 세운다. 시도 횟수는 지우지 않는다 - 몇 번째인지 모르면
    영원히 도는 것을 알아챌 수 없다.
    """

    def apply(row):
        if row["state"] != FAILED:
            raise ValueError("실패한 것만 다시 세울 수 있습니다.")

        if not row.get("retryable"):
            # 토큰이 없어서 죽은 것을 다시 세우면 또 죽는다. 사람이
            # 바깥에서 할 일이 있다는 뜻이고, 줄은 그것을 해결할 수 없다.
            raise ValueError(
                "다시 해도 같은 이유로 실패합니다: " + row.get("reason", ""))

        row["state"] = PENDING
        row["started_at"] = ""
        row["finished_at"] = ""

    return _change(store_path, item_id, apply)


def recover_stuck(store_path: str) -> list:
    """
    올리던 중에 끊긴 것을 다시 세운다. 켤 때 한 번 부른다.

    UPLOADING 인 채로 남아 있으면 아무도 집지 않는다 - 사람은
    올라가는 중인 줄 알고 기다린다.
    """

    data = _read(store_path)
    woken = []

    for row in data["items"]:
        if row["state"] != UPLOADING:
            continue

        row["state"] = PENDING
        row["started_at"] = ""
        row["reason"] = INTERRUPTED
        row["retryable"] = True

        woken.append(row)

    if woken:
        _write(store_path, data)

    return woken
