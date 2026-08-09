"""
Sprint192 - 지금을 한 장으로 떠 둔다 (Epic 59, Phase 15).

Beta Summary와 Beta Readiness가 각각 지금을 말한다. 그런데 그 둘을
따로 부르면 사이가 벌어질 수 있고, "이때 확인했다"는 시각도 없다.

한 번 읽고 나눠 준다
--------------------
Sprint190에서 정한 그 규칙을 여기서도 지킨다. 따로 읽으면 한 장 안에서
숫자가 서로 어긋난다 - 그러려고 beta_readiness가 이미 만든 summary를
받을 수 있게 했다.

떠 두기만 하고 적지는 않는다
----------------------------
'스냅샷'이라는 말은 파일로 남긴다는 뜻으로 읽히기 쉽다. 여기서는
남기지 않는다 - 남기면 그것이 또 어디에 쌓이는지, 언제 지워지는지,
개인의 것이 들어가지 않는지를 다시 설명해야 한다.

그 사실을 note가 직접 말한다. 안 그러면 사람이 나중에 그 파일을
찾는다.

다시 판정하지 않는다
--------------------
O/X/? 도 흐름의 숫자도 앞의 두 자리가 낸 그대로다. 여기서 더하거나
고르는 것이 없다.
"""

import datetime

NOTE = (
    "이 화면은 지금을 읽은 것일 뿐이고 저장되지 않습니다. 남기시려면 "
    "[진단 정보 복사]로 복사해 두십시오."
)


def build() -> dict:
    """
    지금을 한 장으로. 읽기만 하고 적지 않는다.

    확인 시각만 여기서 새로 안다 - 나머지는 전부 앞의 두 자리가
    낸 답이다.
    """

    from app import app_info
    from app.services import beta_readiness, beta_summary

    summary = beta_summary.build()
    readiness = beta_readiness.build(summary)

    flow = [
        {"key": row["key"], "label": row["label"], "count": row["count"]}
        for row in summary["funnel"]["steps"]
    ]

    return {
        "taken_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "version": app_info.VERSION,
        "installations": summary["installations"],
        "flow": flow,
        "readiness": {
            "checks": readiness["checks"],
            "passed": readiness["passed"],
            "failed": readiness["failed"],
            "unknown": readiness["unknown"],
            "caution": readiness["caution"],
        },
        "warnings": list(readiness.get("warnings") or []),
        "note": NOTE,
    }
