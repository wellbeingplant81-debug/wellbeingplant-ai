"""
Sprint177 - 보내온 것을 우리가 바로 읽을 수 있게 (Epic 58, Phase 9).

Sprint175·176이 "어디까지 갔는가"를 적기 시작했다. 그런데 그것을
우리에게 보내려면 지금은 파일을 찾아 열어 통째로 붙여야 한다.
곤란해진 사람에게 그것까지 시키면 대개 안 보낸다.

그래서 보낼 것을 한 덩이로 만든다. 누르면 복사되고, 붙여넣으면
우리가 읽을 수 있는 글이다.

무엇을 담지 않는가가 먼저다
---------------------------
    파일 경로     프로젝트명     사용자명
    대본 내용     이미지 이름    영상 이름    mp4 위치

울타리를 여기서 다시 세우지 않는다
----------------------------------
beta_telemetry가 애초에 그런 것을 적지 않는다. 여기서는 그 안에 있는
것만 옮긴다 - 이 파일이 원본을 직접 열면 울타리 밖으로 나가는 길이
생긴다. 그래서 파일을 열지 않고, summary()와 events()만 받는다.
테스트가 그 사실을 소스에서 확인한다.

아무것도 적지 않는다
--------------------
만들기만 하고 남기지 않는다. 보낼 것을 만드는 일이 새 파일을 남기면
그 파일이 또 어디에 쌓이는지 설명해야 한다.
"""

import datetime

# 이 꾸러미의 판. 받아 보는 쪽이 모양이 바뀐 것을 알아볼 수 있게 한다.
VERSION = 1

# 꾸러미에 들어가는 것 전부. 여기 없는 것은 담지 않는다.
FIELDS = (
    "version",
    "app_version",
    "created_at",
    "launch_count",
    "last_event",
    "last_error_kind",
    "flow_summary",
)

# 흐름에 남기는 줄 수. 넘으면 뒤에서부터 남긴다 - 사람이 방금 겪은
# 일이 그쪽에 있다.
MAX_FLOW = 30


def _flow(events) -> list:
    """
    어디까지 갔는가. 이름만 차례대로.

    잇달아 같은 것이 오면 한 번으로 본다 - 같은 줄이 열 번 이어지는
    것은 읽는 사람에게 아무 말도 하지 않는다.

    떨어져서 다시 나오는 것은 그대로 둔다. 한 번 실패하고 다시 만든
    사람과 한 번에 된 사람은 다른 사람이고, 그 차이가 이야기다.
    """

    found = []

    for entry in events or []:
        name = entry.get("event")

        if not name or (found and found[-1] == name):
            continue

        found.append(name)

    return found[-MAX_FLOW:]


def package() -> dict:
    """
    보낼 것 한 덩이. 만들기만 하고 적지 않는다.

    값은 전부 beta_telemetry가 이미 들고 있던 것이다 - 여기서 새로
    알아내는 것은 "지금이 언제인가" 하나뿐이다.
    """

    from app import app_info
    from app.services import beta_telemetry

    found = beta_telemetry.summary()

    return {
        "version": VERSION,
        "app_version": app_info.VERSION,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "launch_count": found["launch_count"],
        "last_event": found["last_event"],
        "last_error_kind": found["last_error_kind"],
        "flow_summary": _flow(beta_telemetry.events()),
    }


def report() -> str:
    """
    사람이 붙여 넣을 글. 서버가 짓는다.

    화면이 제 나름대로 조립하면 받아 보는 글의 모양이 사람마다 달라
    무엇이 빠졌는지 알 수 없다(Sprint174에서 정한 규칙).
    """

    from app import app_info

    found = package()

    flow = found["flow_summary"] or ["아직 만들기를 시작하지 않았습니다"]

    return "\n".join([
        f"{app_info.NAME} 베타 피드백",
        "",
        "버전:",
        found["app_version"],
        "",
        "마지막 상태:",
        found["last_event"] or "아직 없음",
        "",
        "최근 오류:",
        found["last_error_kind"] or "없음",
        "",
        "사용 흐름:",
        *flow,
    ])
