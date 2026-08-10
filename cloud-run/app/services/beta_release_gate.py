"""
Sprint199 - 배포 확인 정보를 한 장으로 (Epic 59, Phase 17).

Sprint191~198이 만든 자리들이 각각 제 이야기를 한다. 내보낼지 정하려는
사람은 그것을 네 번 눌러 봐야 했다.

이름이 Gate지만 문을 여닫지 않는다
----------------------------------
여기서 하는 일은 "지금 확인된 것"과 "아직 모르는 것"을 한 자리에
늘어놓는 것뿐이다. 문을 열지 말지는 사람이 정한다.

그래서 "배포 가능" 같은 말을 만들지 않는다. 여섯 줄이 전부 O여도 그것은
그 여섯 가지가 확인됐다는 뜻이지 내보내도 된다는 뜻이 아니고, 그 말은
beta_readiness의 caution이 이미 하고 있다. 그것을 그대로 실어 나른다.

세지 않는다
-----------
숫자 하나를 더하는 순간 이 표와 앞의 화면들이 다른 말을 하게 되고,
받아 본 사람은 어느 쪽이 맞는지 알 수 없다. 그래서 이 파일에는 세는
코드가 없다 - 테스트가 소스를 AST로 보고 확인한다.

기록은 한 번만 읽는다
---------------------
Sprint190·192·193이 같은 원칙을 세 번 세웠다. Gate는 그 사슬의 마지막
이라, 여기서 두 번 읽으면 앞의 셋이 지킨 것이 마지막 한 장에서
무너진다.

    beta_summary.build()              <- 기록을 읽는 유일한 자리
        -> beta_snapshot.build(summary)
            -> beta_release_report.build(snapshot)

snapshot에 summary를 넣어 주는 주입구는 Sprint199에서 열었다.
beta_readiness가 Sprint192에 받은 것과 같은 모양이다.

diagnostic은 다시 묻지 않는다
-----------------------------
"진단 정보가 되는가"는 beta_readiness가 이미 물어보고 그 답을
checks의 한 줄로 담아 두었다. 여기서 diagnostic_report를 또 부르면
그것이 두 번째 읽기가 되고, 두 답이 어긋날 수 있다.
"""

NOTE = (
    "이 화면은 지금을 읽은 것일 뿐이고 저장되지 않습니다. 여기 있는 것은 "
    "확인된 사실과 아직 모르는 것뿐이며, 내보낼지는 사람이 정합니다."
)

DIAGNOSTIC = "diagnostic"


def _diagnostic_of(readiness: dict) -> dict:
    """
    진단 정보 줄. readiness가 이미 낸 답에서 그 줄을 집어 온다.

    고르는 것이 아니라 이름으로 찾는 것이다 - 어느 줄이 중요한지를
    여기서 정하지 않는다.
    """

    for row in readiness["checks"]:
        if row["key"] == DIAGNOSTIC:
            return row

    return {"key": DIAGNOSTIC, "label": "진단 정보", "ok": None,
            "detail": "확인한 줄이 없습니다."}


def build() -> dict:
    """
    배포를 정하려는 사람이 보는 한 장. 읽기만 하고 적지 않는다.

    담기는 값은 전부 앞의 자리들이 낸 그대로다. 여기서 새로 만드는
    것은 note 하나뿐이고, 그것도 판정이 아니라 이 표가 무엇이 아닌지를
    말하는 글이다.
    """

    from app import app_info
    from app.services import beta_release_report, beta_snapshot, beta_summary

    summary = beta_summary.build()
    snapshot = beta_snapshot.build(summary)
    release = beta_release_report.build(snapshot)

    readiness = snapshot["readiness"]

    return {
        "taken_at": snapshot["taken_at"],
        "version": app_info.VERSION,

        # 1. 베타 현황 - summary가 위로 꺼내 둔 그대로.
        "summary": {
            "installations": summary["installations"],
            "started": summary["started"],
            "finished": summary["finished"],
            "success_rate": summary["success_rate"],
            "top_blocked_stage": summary["top_blocked_stage"],
            # Sprint206 - 자료까지 갖춘 기록. flow 다섯 칸에는 없는
            # 숫자라 여기로 실어 나른다 - funnel의 칸을 늘리면 칸
            # 사이의 낙차 판정이 전부 달라진다.
            "preparation_ready":
                summary["dashboard"]["preparation_ready"],
            "error_kinds": summary["error_kinds"],
            "next_action": summary["next_action"],
        },

        # 2. 지금 확인되는 것들 - O/X/? 와 각 줄의 설명.
        "readiness": {
            "checks": readiness["checks"],
            "passed": readiness["passed"],
            "failed": readiness["failed"],
            "unknown": readiness["unknown"],
            "caution": readiness["caution"],
        },

        # 3. 언제 본 것인가.
        "snapshot": {
            "taken_at": snapshot["taken_at"],
            "note": snapshot["note"],
        },

        # 4. 밖으로 내보낼 한 장 - 붙여 넣을 글까지 이미 지어져 있다.
        "release": {
            "version": release["version"],
            "checked_at": release["checked_at"],
            "funnel": release["funnel"],
            "cautions": release["cautions"],
            "report": release["report"],
        },

        # 5. 진단 정보가 되는가.
        "diagnostic": _diagnostic_of(readiness),

        "warnings": list(snapshot["warnings"]),
        "note": NOTE,
    }
