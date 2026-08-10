"""
Sprint184 - 베타가 어디에서 멈추는지 한눈에 (Epic 59, Phase 7).

기록은 설치본마다 하나다
------------------------
beta_usage.json은 그 사람의 PC에만 있다. 우리 PC에서 그것을 세면
언제나 "1"이 나온다 - 우리 것 하나뿐이기 때문이다.

그것을 "사용자 수"라고 부르면 거짓이 된다. 그래서 둘을 한다.

    1. 받은 기록을 모아 둘 자리를 만든다
       <관측 기록>/collected/ 에 보내온 beta_usage.json을 넣으면
       그때부터 함께 세어진다.

    2. 몇 벌을 보고 세었는지 함께 말한다
       installations. 화면이 그것을 그대로 보여 준다.

아무것도 안 넣으면 내 것 하나를 센 것이고, 화면이 그렇게 말한다.

세기만 한다
-----------
판정하지 않는다. 어느 단계까지 갔는지는 beta_telemetry가 적어 둔
사건 이름의 차례로만 정한다 - 여기서 "이 사람은 사실 여기서 막혔다"
같은 것을 새로 판단하지 않는다.

읽기만 한다
-----------
보내온 파일을 옮기거나 고치지 않는다. 하나가 깨져 있어도 나머지를
세고, 몇 개를 못 읽었는지 말한다 - 여기서 죽으면 화면 전체가 안 뜬다.
"""

import json
import os

from app.services import beta_telemetry

# 받은 기록을 넣어 두는 폴더 이름.
COLLECTED_DIRNAME = "collected"

# 걸음의 차례. beta_telemetry가 적는 이름을 그대로 쓴다.
#
# 여기서 새 이름을 지으면, 적히는 이름과 세는 이름이 어긋난 채로
# 아무도 모르게 0이 나온다.
WORKSPACE_SELECTED = beta_telemetry.WORKSPACE_SELECTED
SCRIPT_READY = beta_telemetry.SCRIPT_READY
RENDER_STARTED = beta_telemetry.RENDER_STARTED
DONE = "done"

# 어디까지 갔는지를 재는 차례. 앞의 것을 지나야 뒤로 간다.
ORDER = (
    WORKSPACE_SELECTED,
    SCRIPT_READY,
    RENDER_STARTED,
    beta_telemetry.RENDER_COMPLETED,
)

# 막힌 자리로 셀 수 있는 칸들. 아무도 없어도 0으로 적는다 - 없는 줄이
# 사라지면 "그 단계가 없다"로 읽힌다.
STAGES = (
    "start",                 # 켜기만 하고 아무것도 안 함
    WORKSPACE_SELECTED,      # 폴더까지 고르고 멈춤
    SCRIPT_READY,            # 대본까지 넣고 멈춤
    RENDER_STARTED,          # 만들기 시작하고 멈춤
    DONE,                    # 끝까지 감
)

# 세어서 내주는 사건들.
#
# Sprint206 - preparation_ready 가 여기 없었다. 적히기는 하는데
# (studio.py, 프로젝트당 한 번) 아무도 세지 않아서, 모든 기록에 들어
# 있는 숫자를 아무도 읽지 못했다.
#
# ORDER 와 STAGES 에는 넣지 않는다. 넣으면 blocked_stage 바구니가
# 달라지고, 어제까지 script_ready 에서 멈춘 것으로 세어지던 사람이
# 오늘부터 다른 칸으로 옮겨간다 - 그것은 이미 내려진 판정을 바꾸는
# 일이라 따로 정할 문제다.
#
# 그래서 지금도 "자료를 못 모아 못 간 사람"과 "다 모아 놓고 안 누른
# 사람"은 같은 칸에 있다. 다만 자료까지 간 기록이 몇 벌인지는 이제
# 말할 수 있다.
COUNTED = (
    WORKSPACE_SELECTED,
    SCRIPT_READY,
    beta_telemetry.PREPARATION_READY,
    RENDER_STARTED,
    beta_telemetry.RENDER_COMPLETED,
    beta_telemetry.RENDER_FAILED,
)


def collected_root() -> str:
    """받아 온 기록을 넣어 두는 자리."""

    from app import runtime_paths

    return os.path.join(runtime_paths.dataset_root(), COLLECTED_DIRNAME)


def _sent() -> tuple:
    """
    보내온 기록들. (읽은 것들, 못 읽은 개수).

    옮기거나 고치지 않는다 - 남이 보낸 것이다.
    """

    found, broken = [], 0

    try:
        names = sorted(os.listdir(collected_root()))
    except OSError:
        return found, broken

    for name in names:
        if not name.lower().endswith(".json"):
            continue

        try:
            with open(os.path.join(collected_root(), name),
                      encoding="utf-8") as f:
                record = json.load(f)
        except Exception:
            broken += 1
            continue

        if isinstance(record, dict):
            found.append(record)
        else:
            broken += 1

    return found, broken


def _mine() -> dict:
    """
    내 기록. 켠 적이 없으면 세지 않는다.

    빈 것을 한 벌로 세면 "설치본 1"이 늘 나오고, 그 숫자는 아무것도
    말해 주지 않는다.
    """

    summary = beta_telemetry.summary()

    found = {
        "launch_count": summary["launch_count"],
        "events": beta_telemetry.events(),
        # Sprint185 - 내 것의 오류 종류도 함께 센다. 빼 두면 보내온
        # 것만 세어져서 내 PC에서 난 오류가 통계에서 사라진다.
        "last_error_kind": summary.get("last_error_kind"),
    }

    return found if found["launch_count"] or found["events"] else None


def _reached(events) -> str:
    """
    이 기록이 어디까지 갔는가. 적힌 이름의 차례로만 정한다.

    끝까지 갔으면 막힌 것이 아니다.
    """

    names = {entry.get("event") for entry in (events or [])}

    if beta_telemetry.RENDER_COMPLETED in names:
        return DONE

    furthest = "start"

    for stage in ORDER[:-1]:
        if stage in names:
            furthest = stage

    return furthest


def build() -> dict:
    """
    베타가 어디에서 멈추는지. 세기만 한다.

    installations 를 함께 준다 - 몇 벌을 보고 센 것인지 말하지 않으면
    "사용자 1명"이 베타 참가자가 한 명이라는 뜻으로 읽힌다.
    """

    records, broken = _sent()

    mine = _mine()

    if mine:
        records = [mine] + records

    counted = {name: 0 for name in COUNTED}
    blocked = {stage: 0 for stage in STAGES}
    launches = 0

    # Sprint185 - 무엇에 걸렸는지도 센다. 세는 일은 이 한 자리에서만
    # 한다 - 두 자리가 각각 세면 화면마다 다른 숫자가 뜬다.
    #
    # 종류만 적힌다. beta_telemetry가 애초에 메시지를 담지 않는다.
    kinds = {}

    # Sprint189 - 어느 단계에서 무슨 오류가 났는가.
    #
    # 기록 한 벌 안에 "어디까지 갔는가"와 "마지막에 무엇에 걸렸는가"가
    # 함께 적혀 있다. 그 둘을 한 벌 안에서 읽는 것은 사람을 가려내는
    # 일이 아니다.
    by_stage = {stage: {} for stage in STAGES}

    for record in records:
        kind = record.get("last_error_kind")

        events = record.get("events") or []
        names = [entry.get("event") for entry in events]
        stage = _reached(events)

        if kind:
            kinds[kind] = kinds.get(kind, 0) + 1
            by_stage[stage][kind] = by_stage[stage].get(kind, 0) + 1

        launches += int(record.get("launch_count") or 0)

        for name in COUNTED:
            if name in names:
                counted[name] += 1

        blocked[stage] += 1

    return {
        "installations": len(records),
        "unreadable": broken,
        "users_started": len(records),
        "launch_count": launches,
        "workspace_selected": counted[WORKSPACE_SELECTED],
        "script_ready": counted[SCRIPT_READY],
        # Sprint206 - 자료까지 갖춘 기록. 세기만 한다.
        "preparation_ready": counted[beta_telemetry.PREPARATION_READY],
        "render_started": counted[RENDER_STARTED],
        "render_completed": counted[beta_telemetry.RENDER_COMPLETED],
        "render_failed": counted[beta_telemetry.RENDER_FAILED],
        "blocked_stage": blocked,
        "error_kinds": kinds,
        "error_by_stage": by_stage,
        # 받아 온 것을 어디에 넣으면 되는지. 화면이 그대로 보여 준다.
        "collected_dirname": COLLECTED_DIRNAME,
    }
