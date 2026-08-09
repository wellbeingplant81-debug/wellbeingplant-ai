"""
Sprint190 - 베타 운영 정보를 한 장으로 (Epic 59, Phase 13).

Sprint184부터 다섯 자리가 각각 제 이야기를 하게 됐다. 보려면 다섯
번 눌러야 했고, 누를 때마다 기록을 다시 읽었다.

기록을 한 번만 읽는다
---------------------
다섯이 각각 읽으면 그 사이에 파일이 바뀔 수 있다. 그러면 한 화면
안에서 숫자가 서로 어긋난다 - 설치본은 5벌인데 흐름은 6벌에서 센
것처럼.

그래서 beta_dashboard를 한 번 읽고, 그 하나를 다섯에게 나눠 준다.
그 사실은 테스트가 호출 횟수로 확인한다.

새로 세지 않는다
----------------
여기서 더하거나 고르는 것이 없다. 다섯이 낸 답을 그대로 담고, 화면이
자주 보는 것만 위로 꺼내 놓는다.

    installations       몇 벌을 보고 센 것인가
    started / finished  시작과 끝
    top_blocked_stage   가장 많이 멈춘 곳(겹치면 없음)
    next_action         이미 가리키고 있는 그 안내
    error_kinds         자주 난 오류

원인을 말하지 않는다
--------------------
다섯 중 어느 자리도 "왜"를 말하지 않는다. 그것을 여기서 지어내면
앞의 다섯이 지킨 것이 마지막 한 장에서 무너진다.
"""

from app.services import (
    beta_action_tracking, beta_actions, beta_dashboard, beta_feedback_loop,
    beta_funnel, beta_insights,
)


def build() -> dict:
    """
    한 장으로 본 베타 현황. 읽기만 한다.

    기록은 한 번만 읽는다 - 다섯이 같은 한 벌을 보고 말하게 하기
    위해서다.
    """

    dashboard = beta_dashboard.build()

    insights = beta_insights.build(dashboard)
    funnel = beta_funnel.build(dashboard)
    feedback = beta_feedback_loop.build(dashboard)

    action = beta_actions.build(insights)
    progress = beta_action_tracking.build(action)

    notes = list(funnel.get("notes") or [])

    return {
        # 화면이 자주 보는 것.
        "installations": dashboard["installations"],
        "started": funnel["started"],
        "finished": funnel["finished"],
        "success_rate": funnel["success_rate"],
        "top_blocked_stage": insights["top_blocked_stage"],
        "next_action": action.get("action"),
        "error_kinds": insights["common_failures"],
        "notes": notes,

        # 다섯이 낸 답 그대로. 화면이 더 깊이 볼 때 쓴다.
        "dashboard": dashboard,
        "insights": insights,
        "funnel": funnel,
        "feedback": feedback,
        "action": action,
        "progress": progress,
    }
