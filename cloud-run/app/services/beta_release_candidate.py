"""
Sprint200 - 처음 받아서 켠 사람이 끝까지 갈 수 있는가 (Epic 59, Phase 18).

Sprint191~199가 만든 것은 운영자가 보는 층이었다. 이번은 방향이 다르다 -
처음 켠 사람의 여덟 걸음을 따라간다.

가 봤다고 말하지 않는다
-----------------------
우리는 기록을 읽을 뿐이고, 실제로 걸어 본 것이 아니다. 그래서 여기서
할 수 있는 말은 셋뿐이다.

    지금 확인되는 것
    아직 세는 자리가 없는 것
    다음에 할 일

"통과"라고 말하지 않는다. 여덟 줄이 전부 O여도 그것은 그 여덟 가지가
확인됐다는 뜻이지 내보내도 된다는 뜻이 아니고, 그 말은 beta_readiness의
caution이 이미 하고 있다.

여기서 > 0 을 만들지 않는다
---------------------------
그 비교 자체가 새 기준이다. beta_readiness는 이미 script_ready > 0을
판정해 free_flow 줄에 담아 두었다. 그 답을 옮기는 것과, 여기서 다시
재는 것은 다르다 - 후자는 두 자리가 다른 기준을 갖게 되는 첫걸음이다.

그래서 각 걸음은 숫자를 그대로 싣고, ok는 **이미 판정된 줄이 있을
때만** 그 값을 옮긴다. 없으면 None이다.

다섯째 걸음은 모른다
--------------------
자료가 갖춰졌다는 사건의 이름은 preparation_ready 이고, 기록에는
남는다. 그런데 beta_dashboard는 그것을 모아 세지 않는다 - 다섯만 센다.

세는 자리를 새로 만드는 것은 새 데이터 수집이라 하지 않는다. X로 찍으면
"실패했다"로 읽히고 O로 찍으면 거짓이므로, 모른다고 한다.

기록은 한 번만 읽는다
---------------------
beta_release_gate가 이미 기록을 한 번 읽고 그 답을 전부 들고 있다.
여기서 beta_summary나 beta_readiness를 다시 부르면 그것이 두 번째
읽기가 되고, 네 스프린트가 지킨 원칙이 무너진다.

onboarding_state는 기록이 아니라 디스크의 현재 상태를 본다. 사는 자리가
달라 겹치지 않는다.
"""

NOTE = (
    "처음 쓰는 사람의 여덟 걸음을 기록으로 따라간 것입니다. 실제로 걸어 "
    "본 것이 아니므로, 확인된 것과 아직 모르는 것만 적었습니다."
)

# Sprint207 - 이 한 장이 담고 있는 것들.
#
# 머리줄에 누를 것이 열둘이고, 그중 넷은 서로를 담는 관계다. 그 사실을
# 아무도 말하지 않아 운영자는 넷을 눌러 봤고, 넷은 서로 다른 순간을
# 말했다(실측: 배포 확인 정보 13:04:24, Beta Snapshot 13:04:25).
#
# 하나만 눌러도 되면 읽기가 한 번이고, 한 번이면 한 순간이다.
#
# 여기 적는 것은 이름뿐이다. 담고 있다는 것 자체는 코드가 이미 그런
# 것이고(gate를 부르고 그 안에 snapshot이 있다), 그것이 사실인지는
# 값으로 확인한다(test_operator_view.TheHoldingIsTrueTest).
HOLDS = (
    "배포 확인 정보",
    "Beta Snapshot",
    "Beta Summary",
    "Beta Readiness",
    "Release Report",
)

HOLDS_LINE = "이 한 장에 다음이 들어 있습니다 - " + " · ".join(HOLDS)

# 다섯째 걸음. Sprint206에서 수를 얻었지만 판정은 여전히 없다.
#
# "몇 벌이 거기까지 갔다"와 "그것으로 충분한가"는 다른 말이다. 후자를
# 묻는 자리가 없으므로 ok는 ? 그대로다 - 숫자가 생겼다고 판정이 생긴
# 것이 아니다.
ASSETS_DETAIL = "자료가 갖춰진 기록 {}벌. 갖췄는지 판정하는 자리는 없습니다."

# (열쇠, 사람이 읽는 이름, flow의 어느 칸인가, readiness의 어느 줄인가)
#
# 셋째 자리가 None이면 댈 숫자가 없다는 뜻이고, 넷째가 None이면 이미
# 판정된 줄이 없다는 뜻이다.
WALK = (
    ("install", "새 자리 설치", None, "executable"),
    ("first_run", "첫 실행", "시작", None),
    ("workspace", "자료 연결", "자료 연결", None),
    ("script", "대본 준비", "대본 준비", "free_flow"),
    ("assets", "이미지·음성 자료", None, None),
    ("render_started", "제작 시작", "제작 시작", None),
    ("render_completed", "렌더 완료", "렌더 완료", "render_done"),
    ("output", "결과 확인", None, None),
)


def _counts_of(gate: dict) -> dict:
    """flow의 칸 이름 -> 숫자. Gate가 낸 것을 옮기기만 한다."""

    return {row["label"]: row["count"] for row in gate["release"]["funnel"]}


def _marks_of(gate: dict) -> dict:
    """readiness의 줄 이름 -> 이미 내려진 판정."""

    return {row["key"]: row for row in gate["readiness"]["checks"]}


def _detail_for(key: str, mark: dict, state: str, assets=None) -> str:
    if key == "assets":
        return ASSETS_DETAIL.format(assets)

    if key == "output":
        return f"지금 이 설치본은 {state} 입니다."

    if mark:
        return mark["detail"]

    return "기록에 남은 수만 적었습니다."


def _walk(gate: dict, state: str) -> list:
    """
    여덟 걸음. 숫자도 표시도 앞의 자리들이 낸 그대로다.
    """

    counts = _counts_of(gate)
    marks = _marks_of(gate)

    # Sprint206 - 자료까지 갖춘 기록. flow 다섯 칸에 없는 숫자라
    # Gate가 따로 실어 온다.
    assets = gate["summary"]["preparation_ready"]

    steps = []

    for key, label, at, judged in WALK:
        mark = marks.get(judged) if judged else None

        steps.append({
            "key": key,
            "label": label,
            "count": assets if key == "assets"
            else (counts.get(at) if at else None),
            "ok": mark["ok"] if mark else None,
            "detail": _detail_for(key, mark, state, assets),
        })

    return steps


def build(store_path: str, project_path: str = None) -> dict:
    """
    처음 쓰는 사람의 자리에서 본 한 장. 읽기만 하고 적지 않는다.

    store_path     내 자료 폴더를 적어 둔 자리
    project_path   보고 있는 프로젝트. 없으면 아직 아무것도 없는 것
    """

    from app.services import beta_release_gate, onboarding_state

    gate = beta_release_gate.build()
    now = onboarding_state.build(store_path, project_path)

    return {
        "taken_at": gate["taken_at"],
        "version": gate["version"],

        # 지금 이 설치본은 어디에 있는가. 다음에 할 일까지 여기 있다.
        "now": {
            "state": now["state"],
            "title": now["title"],
            "message": now["message"],
            "next_action": now["next_action"],
            "can_continue": now["can_continue"],
            "reasons": now["reasons"],
            "steps": now["steps"],
        },

        # 여덟 걸음.
        "journey": _walk(gate, now["state"]),

        # 무엇에 걸렸는가. Gate가 낸 그대로다.
        "errors": gate["summary"]["error_kinds"],
        "top_blocked_stage": gate["summary"]["top_blocked_stage"],

        "cautions": gate["release"]["cautions"],

        # 무엇이 이 안에 들어 있는가. 넷을 눌러 보지 않아도 되게.
        "holds": list(HOLDS),

        # 붙여 넣어 보내는 글에도 적는다 - 받아 본 사람은 화면을 못
        # 본다. 글을 새로 짓지 않고 이미 지어진 것 뒤에 한 줄을 붙인다.
        "report": gate["release"]["report"] + "\n\n" + HOLDS_LINE,
        "note": NOTE,
    }
