"""
Sprint189 - 피드백과 단계를 잇는다 (Epic 59, Phase 12).

사양은 "현재 단계별 의견 - 자료 연결 3건"을 그리라고 했다. 그런데
그 숫자를 만들 자료가 이 저장소에 없다.

없는 것을 확인한 자리
---------------------
    피드백은 사람이 자유롭게 쓴 글 파일이다(Sprint174)
    그 글에 "나는 자료 연결에서 막혔다"고 적혀 있지 않다
    그 글을 읽지도 않는다 - 경로·파일명·내용이 전부 남의 것이다
    글과 기록을 짝지으면 그것이 곧 사용자 식별이다

그래서 '의견 건수'를 지어내지 않는다. 대신 실제로 있는 것을 단계에
붙인다.

    stopped   그 단계에서 멈춘 설치본이 몇 벌인가
    errors    그 단계에서 무슨 오류가 났는가
    files     내 PC의 피드백 폴더에 글이 몇 개인가(개수만)

이름을 정확히 붙인다
--------------------
"의견 3건"이라고 부르면 누군가 그 셋을 읽으려 든다. 있는 것은
"그 단계에서 멈춘 설치본 3벌"이다. 그 차이를 notes가 직접 말한다.

오류를 단계에 붙이는 것은 짝짓기가 아니다
-----------------------------------------
기록 한 벌 안에 "어디까지 갔는가"와 "마지막에 무엇에 걸렸는가"가
함께 적혀 있다. 그 둘을 한 벌 안에서 읽는 것은 사람을 가려내는
일이 아니다.

원인을 말하지 않는다
--------------------
"자료 연결에서 둘이 멈췄고 WorkspaceError가 둘"까지가 이 자리의
몫이다. 왜 그랬는지는 그 사람에게 물어봐야 안다.
"""

import os

from app.services import beta_dashboard

# 사람이 읽는 단계 이름. beta_dashboard의 열쇠에 붙인다.
LABELS = {
    "start": "켜기만 함",
    beta_dashboard.WORKSPACE_SELECTED: "자료 연결",
    beta_dashboard.SCRIPT_READY: "대본 준비",
    beta_dashboard.RENDER_STARTED: "제작 시작",
    beta_dashboard.DONE: "끝까지 감",
}

# 이 숫자가 무엇이 아닌지. payload가 직접 들고 다닌다.
NOT_OPINIONS = (
    "단계별 숫자는 '그 단계에서 멈춘 설치본 수'입니다. 의견 건수가 "
    "아닙니다 - 피드백 글에는 어느 단계에서 썼는지가 적히지 않습니다."
)

MINE_ONLY = (
    "피드백 글 개수는 이 PC의 것만입니다. 글은 열지 않고 개수만 "
    "셉니다."
)


def _files() -> int:
    """
    내 피드백 폴더에 글이 몇 개인가. 개수만 센다.

    이름도 내용도 보지 않는다 - 사람이 자유롭게 쓴 글이라 경로도
    대본도 들어 있다.
    """

    from app import runtime_paths

    try:
        names = os.listdir(runtime_paths.feedback_root())
    except OSError:
        return 0

    return len(names)


def build(dashboard: dict = None) -> dict:
    """
    단계마다 무엇이 붙는가. 읽기만 한다.

    dashboard를 주지 않으면 beta_dashboard에게 물어본다 - 화면과 같은
    숫자를 보게 하기 위해서다.
    """

    found = dashboard if dashboard is not None else beta_dashboard.build()

    blocked = found.get("blocked_stage") or {}
    by_stage = found.get("error_by_stage") or {}

    stages = []

    for stage in beta_dashboard.STAGES:
        kinds = by_stage.get(stage) or {}

        stages.append({
            "key": stage,
            "label": LABELS[stage],
            "stopped": int(blocked.get(stage) or 0),
            "errors": [{"kind": kind, "count": count}
                       for kind, count in sorted(
                           kinds.items(), key=lambda row: (-row[1], row[0]))],
        })

    notes = [NOT_OPINIONS, MINE_ONLY]

    if not found.get("installations"):
        notes.append(
            "아직 볼 기록이 없습니다. 받아 오신 beta_usage.json 을 "
            f"{beta_dashboard.COLLECTED_DIRNAME} 폴더에 넣으시면 여기에 "
            "나옵니다.")

    return {
        "stages": stages,
        "feedback_files": _files(),
        "installations": int(found.get("installations") or 0),
        "notes": notes,
    }
