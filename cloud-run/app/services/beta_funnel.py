"""
Sprint188 - 전체 흐름을 한 줄로 (Epic 59, Phase 11).

Sprint184가 단계마다 세어 줬고 Sprint185가 어디가 가장 막히는지
골라 줬다. 그런데 "몇 벌이 시작해서 몇 벌이 끝냈는가"를 한눈에 보는
자리는 아직 없었다.

세지 않는다. 이미 센 것을 늘어놓는다
------------------------------------
beta_dashboard가 낸 숫자만 쓴다 - 두 자리가 각각 세면 화면마다 다른
숫자가 뜬다. 새 사건도 적지 않는다.

깔때기 모양을 억지로 만들지 않는다
----------------------------------
사건은 칸마다 따로 적힌다. 그래서 뒤 칸이 앞 칸보다 클 수 있다 -
Sprint184 실측에 render_started 없이 render_completed만 있는 기록이
실제로 있었다.

그때 숫자를 다듬어 매끈한 깔때기로 만들면 그것은 자료가 아니라
그림이다. 그대로 두고, 그런 칸이 있다고 말한다(irregular).

원인을 말하지 않는다
--------------------
"대본 준비에서 둘이 빠졌다"까지가 이 자리의 몫이다. "왜"는 여기서
말하지 않는다 - 그것을 알려면 그 사람에게 물어봐야 하고, 우리는
묻지 않았다.

없는 것을 0으로 말하지 않는다
-----------------------------
아무도 시작하지 않았으면 성공률은 0%가 아니라 '없음'이다. 0%는
"아무도 못 끝냈다"는 뜻이고 그것은 사실이 아니다.
"""

from app.services import beta_dashboard, beta_insights, beta_telemetry

# "적다"의 기준. 여기서 새로 정하지 않는다 - 두 화면이 다른 기준으로
# "적다"고 하면 사람이 헷갈린다.
ENOUGH = beta_insights.ENOUGH

# 다섯 칸. (열쇠, 사람이 읽는 이름, dashboard의 어느 숫자인가)
STEPS = (
    ("start", "시작", "installations"),
    (beta_dashboard.WORKSPACE_SELECTED, "자료 연결", "workspace_selected"),
    (beta_dashboard.SCRIPT_READY, "대본 준비", "script_ready"),
    (beta_dashboard.RENDER_STARTED, "제작 시작", "render_started"),
    (beta_telemetry.RENDER_COMPLETED, "렌더 완료", "render_completed"),
)


def _share(count: int, first: int):
    """첫 칸을 1로 봤을 때 얼마인가. 첫 칸이 0이면 없음."""

    if not first:
        return None

    return round(count / first, 4)


def build(dashboard: dict = None) -> dict:
    """
    전체 흐름. 셈만 한다.

    dashboard를 주지 않으면 beta_dashboard에게 물어본다 - 화면과 같은
    숫자를 보게 하기 위해서다.
    """

    found = dashboard if dashboard is not None else beta_dashboard.build()

    counts = [int(found.get(source) or 0) for _, _, source in STEPS]
    first = counts[0]

    steps = []
    irregular = False

    for at, (key, label, _) in enumerate(STEPS):
        count = counts[at]
        before = counts[at - 1] if at else count

        # 앞 칸보다 크면 빠진 것이 아니다. 음수를 적지 않는다 -
        # "-2명이 빠졌다"는 말은 뜻이 없다.
        dropped = max(before - count, 0)

        if at and count > before:
            irregular = True

        steps.append({
            "key": key,
            "label": label,
            "count": count,
            "dropped": dropped,
            "share": _share(count, first),
        })

    notes = []

    if not first:
        notes.append(
            "아직 볼 기록이 없습니다. 받아 오신 beta_usage.json 을 "
            f"{beta_dashboard.COLLECTED_DIRNAME} 폴더에 넣으시면 여기에 "
            "나옵니다.")
    elif first < ENOUGH:
        notes.append(
            f"기록이 {first}벌뿐이라 적습니다. 이 숫자로 무엇을 정하기에는 "
            "이릅니다.")

    if irregular:
        notes.append(
            "앞 칸보다 큰 칸이 있습니다. 사건이 칸마다 따로 적히기 "
            "때문이며, 숫자를 다듬지 않고 그대로 둡니다.")

    return {
        "steps": steps,
        "success_rate": _share(counts[-1], first),
        "started": first,
        "finished": counts[-1],
        "empty": not first,
        "thin": 0 < first < ENOUGH,
        "irregular": irregular,
        "notes": notes,
        "enough": ENOUGH,
    }
