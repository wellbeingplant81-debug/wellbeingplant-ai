"""
Sprint185 - 어디를 먼저 고칠 것인가 (Epic 59, Phase 8).

Sprint184가 "어디에서 멈췄는가"를 세어 줬다. 그 숫자를 놓고 "그래서
무엇부터 고칠까"를 정하는 일은 아직 사람이 해야 했다.

세는 일은 여기서 하지 않는다
----------------------------
beta_dashboard가 낸 결과만 읽는다 - 두 자리가 각각 세면 화면마다
다른 숫자가 뜬다.

숫자를 지어내지 않는다
----------------------
    기록이 없으면 없다고 한다
    아무도 없는 단계도 0으로 남긴다
    같은 수로 겹치면 하나를 고르지 않는다
    몇 벌을 보고 한 말인지 함께 낸다

셋째가 특히 중요하다. 겹친 것 중에 하나를 고르면 그것은 자료가
아니라 우리 취향이다.

넷째도 그렇다. 두 벌짜리 기록에서 "가장 많이 막힌 곳"을 단정하면
그것은 자료가 아니라 우연이다. 그래서 적을 때는 적다고 말한다 -
숨기면 그 숫자를 근거로 무언가를 고치게 된다.

끝까지 간 것은 막힌 곳이 아니다
-------------------------------
done이 가장 많아도 그것을 '가장 많이 막힌 단계'라고 부르지 않는다.
"""

from app.services import beta_dashboard

# 이만큼은 봐야 "많다/적다"를 말할 수 있다고 보는 수.
#
# 근거가 있는 숫자가 아니다 - 그래서 이것으로 무엇을 막지 않는다.
# 적으면 적다고 말할 뿐이고, 그 말을 화면이 그대로 보여 준다.
ENOUGH = 5

# 그 단계가 많으면 어디를 들여다보면 되는가. 판정이 아니라 안내다.
#
# Sprint186 - 어느 걸음을 가리키는지 바로잡았다.
#
# blocked_stage는 "그 사건까지 갔고 그 다음으로 못 갔다"는 뜻이다.
# workspace_selected로 세어진 사람은 폴더를 이미 골랐다 - 그 사람에게
# 폴더 안내를 보라고 하면 자기가 이미 한 일을 다시 읽게 된다.
#
# 그래서 가리키는 것은 '그 단계'가 아니라 '그 다음 걸음'이다.
WHERE_TO_LOOK = {
    "start": [
        "켜기만 하고 아무것도 하지 않은 분이 많습니다. 첫 화면의 "
        "안내와 '내 자료 폴더 선택'이 눈에 띄는지 보십시오.",
    ],
    beta_dashboard.WORKSPACE_SELECTED: [
        "폴더까지 고르고 대본 준비로 넘어가지 못한 분이 많습니다. "
        "대본 생성 방식과 요청문 안내를 확인하십시오.",
    ],
    beta_dashboard.SCRIPT_READY: [
        "대본까지 넣고 만들기로 넘어가지 못한 분이 많습니다. 자료 확인 "
        "안내(어느 장면에 무엇이 없는지)를 확인하십시오.",
    ],
    beta_dashboard.RENDER_STARTED: [
        "만들기 시작한 뒤에 멈추는 분이 많습니다. 렌더 실패와 결과 검사 "
        "쪽을 확인하십시오.",
    ],
    beta_dashboard.DONE: [
        "끝까지 가신 분이 많습니다. 지금 막는 것은 보이지 않습니다.",
    ],
}


def _top(blocked: dict):
    """
    가장 많이 막힌 곳. (하나, 겹친 것들).

    끝까지 간 것은 막힌 것이 아니므로 빼고 본다. 아무도 없으면 None,
    같은 수로 겹치면 고르지 않는다.
    """

    counted = {stage: count for stage, count in blocked.items()
               if stage != beta_dashboard.DONE and count}

    if not counted:
        return None, []

    most = max(counted.values())
    tied = sorted(stage for stage, count in counted.items()
                  if count == most)

    return (tied[0] if len(tied) == 1 else None), tied


def _failures(kinds: dict) -> list:
    """
    자주 난 오류. 적힌 것만 적는다.

    없으면 빈 목록이다 - "문제 없음"이라고 말하지 않는다. 아직
    아무도 안 써 본 것과 써 봤는데 문제가 없던 것은 다르다.
    """

    return [{"kind": kind, "count": count}
            for kind, count in sorted((kinds or {}).items(),
                                      key=lambda row: (-row[1], row[0]))]


def _recommendations(top, tied, installations, thin, failures) -> list:
    """무엇을 들여다보면 되는가. 아는 것만 말한다."""

    if not installations:
        return ["아직 볼 기록이 없습니다. 받아 오신 beta_usage.json 을 "
                f"{beta_dashboard.COLLECTED_DIRNAME} 폴더에 넣으시면 "
                "여기에 나옵니다."]

    found = []

    if top:
        found += WHERE_TO_LOOK[top]
    elif tied:
        names = ", ".join(tied)
        found.append(
            f"같은 수로 겹칩니다({names}). 어느 쪽이 더 문제인지는 이 "
            "기록만으로 알 수 없습니다.")
    else:
        found += WHERE_TO_LOOK[beta_dashboard.DONE]

    if thin:
        found.append(
            f"기록이 {installations}벌뿐이라 적습니다. 이 숫자로 무엇을 "
            "정하기에는 이릅니다.")

    if failures:
        top_failure = failures[0]
        found.append(
            f"가장 자주 난 오류는 {top_failure['kind']} "
            f"({top_failure['count']}건)입니다.")

    return found


def build(dashboard: dict = None) -> dict:
    """
    무엇부터 고칠 것인가. 세지 않고 읽기만 한다.

    dashboard를 주지 않으면 beta_dashboard에게 물어본다 - 화면과 같은
    숫자를 보게 하기 위해서다.
    """

    found = dashboard if dashboard is not None else beta_dashboard.build()

    blocked = dict(found.get("blocked_stage") or {})

    # 아무도 없는 단계도 남긴다 - 줄이 사라지면 "그 단계가 없다"로
    # 읽힌다.
    for stage in beta_dashboard.STAGES:
        blocked.setdefault(stage, 0)

    installations = int(found.get("installations") or 0)
    top, tied = _top(blocked)
    failures = _failures(found.get("error_kinds"))
    thin = 0 < installations < ENOUGH

    return {
        "top_blocked_stage": top,
        "top_candidates": tied,
        "tied": len(tied) > 1,
        "stage_counts": blocked,
        "common_failures": failures,
        "recommendations": _recommendations(top, tied, installations,
                                            thin, failures),
        "installations": installations,
        "thin": thin,
        "enough": ENOUGH,
    }
