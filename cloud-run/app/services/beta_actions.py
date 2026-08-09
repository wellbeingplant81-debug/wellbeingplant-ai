"""
Sprint186 - 그래서 어느 안내를 보면 되는가 (Epic 59, Phase 9).

Sprint185가 "가장 많이 막힌 단계"를 알려 줬다. 그런데 그 다음에
무엇을 열어야 하는지는 여전히 사람이 찾아야 했다.

해결 방법을 새로 만들지 않는다
------------------------------
이미 있는 안내가 어디 있는지를 가리키기만 한다.

    first_run_guide   여섯 걸음 중 몇 번째를 보면 되는가
    troubleshooting   무엇이 문제이고 어떻게 하는가

여기서 새 문장을 쓰면 같은 이야기가 두 벌이 되고, 어느 날 한쪽만
바뀐다. 걸음의 이름도 first_run_guide가 정한 것을 그대로 쓴다.

'막힌 단계'가 무슨 뜻인지 조심한다
----------------------------------
beta_dashboard의 blocked_stage는 "그 사건까지 갔고 그 다음으로 못
갔다"는 뜻이다. workspace_selected로 세어진 사람은 폴더를 이미
골랐고, 막힌 곳은 그 다음 걸음이다.

그래서 여기서 여는 것은 '그 단계'가 아니라 '그 다음 걸음'의 안내다.
폴더를 이미 고른 사람에게 폴더 안내를 열어 주면, 그 사람은 자기가
이미 한 일을 다시 읽게 된다.

겹치면 고르지 않는다
--------------------
Sprint185에서 정한 그 규칙을 여기서도 지킨다. 겹친 것 중 하나를 골라
안내를 열어 주면 그것은 자료가 아니라 우리 취향이다.
"""

from app.services import beta_dashboard, first_run_guide

# 열 수 있는 안내들. 화면이 이 이름으로 어디를 열지 정한다.
GUIDE = "first_run_guide"
TROUBLE = "troubleshooting"

TARGETS = (GUIDE, TROUBLE)

# 그 단계까지 간 사람이 다음에 볼 곳.
#
# 값은 (어디를 열까, 여섯 걸음 중 몇 번째). 걸음이 없는 것은 None -
# 그때는 문제 해결 쪽이다.
WHERE = {
    # 켜기만 했다 -> 내 자료 연결부터
    "start": (GUIDE, first_run_guide.WORKSPACE),
    # 폴더까지 골랐다 -> 다음은 대본
    beta_dashboard.WORKSPACE_SELECTED: (GUIDE, first_run_guide.SCRIPT),
    # 대본까지 넣었다 -> 다음은 자료 확인
    beta_dashboard.SCRIPT_READY: (GUIDE, first_run_guide.ASSETS),
    # 만들기 시작하고 못 끝냈다 -> 안내가 아니라 문제 해결
    beta_dashboard.RENDER_STARTED: (TROUBLE, None),
    # 끝까지 갔다 -> 열 것이 없다
    beta_dashboard.DONE: (None, None),
}


def _step(number: int) -> tuple:
    """그 걸음의 이름과 할 일. first_run_guide가 정한 그대로."""

    for step, title, description, action in first_run_guide.STEPS:
        if step == number:
            return title, description, action

    return "", "", ""


def build(insights: dict = None) -> dict:
    """
    어느 안내를 열면 되는가. 판정하지 않는다.

    insights를 주지 않으면 beta_insights에게 물어본다 - 화면과 같은
    답을 보게 하기 위해서다.
    """

    from app.services import beta_insights

    found = insights if insights is not None else beta_insights.build()

    stage = found.get("top_blocked_stage")
    tied = bool(found.get("tied"))
    candidates = list(found.get("top_candidates") or [])
    installations = int(found.get("installations") or 0)

    if not installations:
        return {
            "stage": None, "title": "아직 볼 기록이 없습니다",
            "action": None, "tied": False, "candidates": [],
            "reasons": ["받아 오신 기록이 없어 어디를 고칠지 알 수 "
                        "없습니다."],
            "installations": 0,
        }

    if tied:
        return {
            "stage": None, "title": "어느 쪽인지 가릴 수 없습니다",
            "action": None, "tied": True, "candidates": candidates,
            "reasons": ["같은 수로 겹칩니다. 이 기록만으로는 어느 쪽이 "
                        "더 문제인지 알 수 없습니다."],
            "installations": installations,
        }

    if not stage or stage not in WHERE:
        return {
            "stage": stage, "title": "지금 막는 곳이 보이지 않습니다",
            "action": None, "tied": False, "candidates": candidates,
            "reasons": [], "installations": installations,
        }

    target, number = WHERE[stage]

    if target is None:
        return {
            "stage": stage, "title": "끝까지 가신 분이 가장 많습니다",
            "action": None, "tied": False, "candidates": candidates,
            "reasons": [], "installations": installations,
        }

    if target == TROUBLE:
        return {
            "stage": stage,
            "title": "만들기 시작한 뒤에 멈춤",
            "action": {"label": "문제 해결 열기", "target": TROUBLE,
                       "step": None},
            "tied": False, "candidates": candidates,
            "reasons": [], "installations": installations,
        }

    title, description, action = _step(number)

    return {
        "stage": stage,
        # 걸음의 이름은 first_run_guide의 것이다.
        "title": f"다음 걸음에서 멈춤 - {title}",
        "action": {"label": f"{number}단계 안내 보기 ({action})",
                   "target": GUIDE, "step": number},
        "tied": False,
        "candidates": candidates,
        "reasons": [description],
        "installations": installations,
    }
