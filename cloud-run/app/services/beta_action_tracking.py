"""
Sprint187 - 도움말이 가리킨 걸음에 닿았는가 (Epic 59, Phase 10).

Sprint186이 "어느 안내를 열면 되는가"를 가리켜 줬다. 그 다음 물음은
"그래서 넘어갔는가"다.

말할 수 없는 것을 말하지 않는다
-------------------------------
도움말을 언제 열었는지는 적지 않는다 - 이번 스프린트가 새 기록을
금지했고, 그 결정이 옳다. 그러면 "도움말을 보고 넘어갔다"는 말은 할
수 없다. 그 사이에 무슨 일이 있었는지 우리가 모르기 때문이다.

    도움말을 안 열고도 넘어갈 수 있다
    도움말을 열고도 다른 이유로 넘어갈 수 있다
    도움말을 열기 전에 이미 넘어가 있었을 수도 있다

그래서 이 자리가 말하는 것은 하나뿐이다.

    도움말이 가리킨 그 걸음에 닿은 적이 있는가

닿았다는 것과 도움말 덕분이라는 것은 다르다. 그 차이를 payload가
직접 말한다(caution) - 화면이 "도움말 효과"로 읽지 않게.

새로 판정하지 않는다
--------------------
    beta_actions       무엇을 가리켰는가
    beta_telemetry     그 걸음에 닿은 적이 있는가

읽기만 한다. 물어봤다고 새 사건이 적히면, 그 순간 이 숫자는 우리가
만든 숫자가 된다.
"""

from app.services import beta_actions, beta_telemetry, first_run_guide

# 그 걸음을 넘어갔다고 볼 수 있는 사건.
#
# 이름은 beta_telemetry가 적는 것을 그대로 쓴다 - 여기서 새로 지으면
# 적히는 이름과 재는 이름이 어긋난 채로 영영 "아직"만 나온다.
REACHED_BY = {
    first_run_guide.WORKSPACE: beta_telemetry.WORKSPACE_SELECTED,
    first_run_guide.SCRIPT: beta_telemetry.SCRIPT_READY,
    first_run_guide.ASSETS: beta_telemetry.RENDER_STARTED,
}

# 문제 해결로 보낸 경우. 만들다 멈춘 사람이 넘어갔다는 것은 끝났다는
# 뜻이다.
TROUBLE_REACHED_BY = beta_telemetry.RENDER_COMPLETED

# 이 숫자가 무엇이 아닌지. payload가 직접 들고 다닌다.
CAUTION = (
    "도움말을 언제 열었는지는 적지 않습니다. 그래서 이것은 '그 걸음에 "
    "닿은 적이 있는가'일 뿐이고, 도움말 때문에 넘어갔다는 뜻은 "
    "아닙니다."
)


def reached(event: str):
    """
    그 사건이 적혀 있는가. (있는가, 언제).

    적힌 것을 읽기만 한다 - 지나온 걸음을 없다고 하지 않는다.
    """

    if not event:
        return False, None

    for entry in beta_telemetry.events():
        if entry.get("event") == event:
            return True, entry.get("timestamp")

    return False, None


def _target(help_card: dict):
    """
    무엇으로 "넘어갔다"를 잴 것인가.

    가리킨 것이 없으면 잴 것도 없다 - 그때 억지로 하나를 고르면
    화면이 아무 근거 없는 "아직"을 띄운다.
    """

    action = help_card.get("action")

    if not action:
        return None

    if action.get("target") == beta_actions.TROUBLE:
        return TROUBLE_REACHED_BY

    return REACHED_BY.get(action.get("step"))


def build(help_card: dict = None) -> dict:
    """
    도움말이 가리킨 걸음에 닿았는가. 읽기만 한다.

    닿았다는 것과 도움말 덕분이라는 것은 다르다 - caution이 그 말을
    함께 들고 다닌다.

    Sprint190 - 이미 만들어 둔 카드를 받을 수 있다. 한 화면에서
    여럿이 볼 때 각자 다시 읽으면 그 사이에 기록이 바뀌고, 숫자가
    서로 어긋난다.
    """

    if help_card is None:
        help_card = beta_actions.build()

    event = _target(help_card)
    there, when = reached(event)

    return {
        "help": help_card,
        "target_event": event,
        "reached": there,
        "reached_at": when,
        "caution": CAUTION,
    }
