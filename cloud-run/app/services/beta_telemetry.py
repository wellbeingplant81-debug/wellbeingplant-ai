"""
Sprint175 - 베타 사용자가 어디에서 멈추는지 안다 (Epic 58, Phase 7).

한 명이 써 보고 "잘 안 되던데요"라고 하면 우리가 할 수 있는 것이
없다. 어디까지 갔다가 멈췄는지를 알아야 한다.

무엇을 적지 않는가부터 정한다
-----------------------------
    사람 이름     적지 않는다
    파일 경로     적지 않는다
    영상 내용     적지 않는다
    대본 내용     적지 않는다

관찰은 사람을 들여다보는 일이 되기 쉽다. 그래서 "무엇을 적을까"가
아니라 "무엇은 절대 적지 않는가"를 먼저 정하고, 그 울타리 안에서만
적는다. 울타리는 셋으로 세운다.

    1. 사건 이름은 EVENTS에 있는 것만 받는다
       부르는 쪽이 아무 글자나 넣을 수 있으면 거기로 무엇이든 샌다.

    2. 같은 것인지 가리는 표(once)는 그대로 적지 않는다
       무엇이 표로 올지 우리가 다 알 수 없다. 짧은 지문만 남긴다.

    3. 오류는 '종류'만 적는다
       메시지에는 대개 경로가 들어 있다. 원문은 이미 logs/에 있고,
       그것은 사람이 제 손으로 보내 주는 것이다.

적는 것은 셋뿐이다
------------------
    언제 켰는가        first_launch_at · last_launch_at · launch_count
    어디까지 갔는가    {event, timestamp, version}
    무엇에 걸렸는가    last_error_kind · last_error_time

어디에 적는가
-------------
사용자 자리의 .dataset/ 아래다. 프로그램 폴더에 적으면 새 판을
덮어씌울 때 함께 사라지고, Program Files에 설치했다면 아예 쓸 수도
없다.

    묶였을 때   %APPDATA%\\AI영상제작소\\.dataset\\beta_usage.json
    개발 중     저장소의 .dataset/

.dataset은 "쌓아 온 관측 기록"이 사는 자리로 이미 정해져 있고(Sprint169),
사용 기록이 바로 그것이다. 사용자 자리 바로 아래에 두었더니 개발
중에는 저장소 뿌리에 파일이 떨어졌다 - 프로그램 폴더를 더럽히지
않겠다던 말과 어긋난다.

관찰이 제품을 멈추게 하지 않는다
--------------------------------
적지 못해도 하던 일은 그대로 간다. note()가 그 문을 맡는다 - 다만
모르는 사건 이름은 삼키지 않는다. 그것은 부르는 쪽의 잘못이고,
삼키면 울타리가 있으나 마나가 된다.
"""

import datetime
import hashlib
import json
import os

FILENAME = "beta_usage.json"

# 적을 수 있는 사건. 이 밖의 이름은 받지 않는다.
WORKSPACE_SELECTED = "workspace_selected"
SCRIPT_READY = "script_ready"
PREPARATION_READY = "preparation_ready"
RENDER_STARTED = "render_started"
RENDER_COMPLETED = "render_completed"
RENDER_FAILED = "render_failed"
OUTPUT_CHECK_FAILED = "output_check_failed"

EVENTS = (
    WORKSPACE_SELECTED,
    SCRIPT_READY,
    PREPARATION_READY,
    RENDER_STARTED,
    RENDER_COMPLETED,
    RENDER_FAILED,
    OUTPUT_CHECK_FAILED,
)

# 파일에 있을 수 있는 열쇠 전부. 여기 없는 것은 적지 않는다.
KEYS = (
    "version",
    "first_launch_at",
    "last_launch_at",
    "launch_count",
    "events",
    "seen",
    "last_error_kind",
    "last_error_time",
)

# 오래된 것부터 버린다 - 마지막에 무슨 일이 있었는지가 궁금하다.
MAX_EVENTS = 200

# 오류 '종류'의 길이. 넘으면 자른다 - 부르는 쪽이 실수로 문장을
# 통째로 넘겨도 경로가 통째로 들어오지 않게 한다.
MAX_KIND = 40

VERSION = 1


def path() -> str:
    """기록이 사는 자리. 사용자 자리의 관측 기록 폴더다."""

    from app import runtime_paths

    return os.path.join(runtime_paths.dataset_root(), FILENAME)


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _blank() -> dict:
    return {
        "version": VERSION,
        "first_launch_at": None,
        "last_launch_at": None,
        "launch_count": 0,
        "events": [],
        "seen": [],
        "last_error_kind": None,
        "last_error_time": None,
    }


def _read() -> dict:
    """
    적혀 있는 것. 읽지 못하면 빈 것.

    깨진 파일 하나 때문에 프로그램이 멈추지 않는다 - 관찰은 곁다리다.
    """

    found = _blank()

    try:
        with open(path(), encoding="utf-8") as f:
            stored = json.load(f)
    except Exception:
        return found

    if not isinstance(stored, dict):
        return found

    # 우리가 아는 열쇠만 받는다. 예전 판이 적어 둔 모르는 열쇠가
    # 있어도 여기서 걸러진다.
    for key in KEYS:
        if key in stored:
            found[key] = stored[key]

    found["version"] = VERSION

    return found


def _save(found: dict) -> dict:
    from app import runtime_paths
    from app.utils.atomic_write import atomic_write_json

    runtime_paths.ensure(runtime_paths.dataset_root())
    atomic_write_json(path(), found)

    return found


def launched() -> dict:
    """
    켰다고 적는다. 켤 때 한 번 부른다.

    처음 켠 때는 한 번만 적힌다 - 그것이 "언제부터 쓰기 시작했는가"다.
    """

    found = _read()
    when = _now()

    if not found["first_launch_at"]:
        found["first_launch_at"] = when

    found["last_launch_at"] = when
    found["launch_count"] = int(found.get("launch_count") or 0) + 1

    return _save(found)


def _fingerprint(once: str) -> str:
    """
    같은 것인지 가리는 지문.

    준 글자를 그대로 적지 않는다 - 무엇이 올지 우리가 다 알 수 없고,
    언젠가 거기로 경로나 제목이 들어온다.
    """

    return hashlib.sha256(str(once).encode("utf-8")).hexdigest()[:16]


def record(event: str, once: str = None) -> dict:
    """
    거기까지 갔다고 적는다.

    once를 주면 그 지문으로 한 번만 적는다 - 화면은 렌더가 끝났는지
    1초마다 물어보므로, 물어볼 때마다 적으면 기록이 그 한 번으로
    뒤덮인다.
    """

    if event not in EVENTS:
        raise ValueError(f"적을 수 없는 사건입니다: {event}")

    from app import app_info

    found = _read()

    if once is not None:
        mark = f"{event}:{_fingerprint(once)}"

        if mark in found["seen"]:
            return found

        found["seen"] = (found["seen"] + [mark])[-MAX_EVENTS:]

    found["events"] = (found["events"] + [{
        "event": event,
        "timestamp": _now(),
        "version": app_info.VERSION,
    }])[-MAX_EVENTS:]

    return _save(found)


def failed(kind) -> dict:
    """
    무엇에 걸렸는지 '종류'만 적는다.

    예외를 주면 그 이름을 쓴다. 메시지는 쓰지 않는다 - 거기에는 대개
    경로가 들어 있다. 원문이 필요하면 logs/에 있다.
    """

    if isinstance(kind, BaseException):
        name = type(kind).__name__
    else:
        name = str(kind or "")

    # 이름 자리에 문장이 들어와도 새지 않게 한다.
    name = name.strip().split()[0] if name.strip() else ""
    name = name.replace("\\", "/").split("/")[0][:MAX_KIND]

    found = _read()

    found["last_error_kind"] = name or None
    found["last_error_time"] = _now()

    return _save(found)


def summary() -> dict:
    """화면이 보여 줄 것. 적힌 것을 그대로 옮긴다."""

    found = _read()
    events = found["events"]

    return {
        "launch_count": found["launch_count"],
        "first_launch_at": found["first_launch_at"],
        "last_launch_at": found["last_launch_at"],
        "last_event": events[-1]["event"] if events else None,
        "last_event_at": events[-1]["timestamp"] if events else None,
        "last_error_kind": found["last_error_kind"],
        "last_error_time": found["last_error_time"],
    }


def report() -> str:
    """
    붙여 넣을 글. 서버가 짓는다.

    화면이 제 나름대로 조립하면 받아 보는 글의 모양이 사람마다 달라
    무엇이 빠졌는지 알 수 없다(Sprint174에서 정한 규칙).
    """

    from app import app_info

    found = summary()

    lines = [
        app_info.title(),
        f"실행       {found['launch_count']}회",
        f"마지막     {found['last_launch_at'] or '-'}",
        f"마지막 상태 {found['last_event'] or '-'}"
        + (f" ({found['last_event_at']})" if found["last_event_at"] else ""),
        f"마지막 오류 {found['last_error_kind'] or '-'}"
        + (f" ({found['last_error_time']})" if found["last_error_time"]
           else ""),
    ]

    return "\n".join(lines)


def note(event: str, once: str = None):
    """
    적되, 못 적어도 하던 일은 그대로 간다.

    부르는 쪽(라우터)이 쓰는 문이다. 관찰이 제품을 멈추게 하면
    관찰을 켠 것이 잘못이 된다.

    모르는 사건 이름은 삼키지 않는다 - 그것은 부르는 쪽의 잘못이고,
    삼키면 울타리가 있으나 마나가 된다.
    """

    if event not in EVENTS:
        raise ValueError(f"적을 수 없는 사건입니다: {event}")

    try:
        record(event, once=once)
    except Exception:
        return None

    return None


def note_failure(kind):
    """오류 종류를 적되, 못 적어도 넘어간다."""

    try:
        failed(kind)
    except Exception:
        return None

    return None
