"""
Sprint193 - 밖으로 내보낼 한 장 (Epic 59, Phase 16).

Beta Snapshot은 우리가 보는 화면이다. 그것을 남에게 보내려면 붙여넣을
수 있는 글이어야 하고, 밖으로 나가도 되는 것만 들어 있어야 한다.

스냅샷이 낸 것만 쓴다
---------------------
여기서 세지도 고르지도 않는다. 숫자 하나를 더하는 순간, 이 글과 그
화면이 다른 말을 하게 된다 - 받아 본 사람은 어느 쪽이 맞는지 알 수
없다.

그래서 이 파일은 beta_snapshot 말고 아무에게도 물어보지 않는다. 소스에
다른 서비스 이름이 없는지 테스트가 확인한다.

스냅샷이 이상한 숫자를 줘도 그대로 낸다
---------------------------------------
여기서 고치면 두 화면이 다른 말을 한다. 고칠 것이 있으면 스냅샷을
고쳐야 한다 - 그쪽이 세는 자리다.

밖으로 나가는 글이다
--------------------
경로도 파일명도 프로젝트명도 피드백 내용도 들어가지 않는다. 스냅샷이
애초에 담지 않지만, 이 글은 우리 손을 떠나므로 여기서도 확인한다.
"""

import unicodedata

MARKS = {True: "O", False: "X", None: "?"}


def _pad(text: str, width: int) -> str:
    """
    칸을 맞춘다. 한글은 한 글자가 두 칸을 쓴다.

    글자 수로 맞추면 "시작"과 "자료 연결"의 숫자가 서로 다른 자리에
    찍힌다 - 붙여 넣어 보내는 글이라 그것이 그대로 남는다.
    """

    used = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1
               for ch in text)

    return text + " " * max(0, width - used)


def _text(found: dict) -> str:
    """
    붙여 넣을 글. 스냅샷이 준 값을 늘어놓기만 한다.

    화면이 제 나름대로 조립하면 받아 보는 글의 모양이 사람마다 달라
    무엇이 빠졌는지 알 수 없다(Sprint174에서 정한 규칙).

    O/X/? 는 build()가 이미 붙여 둔 것을 그대로 읽는다. 여기서 다시
    고르면 표와 글이 서로 다른 표시를 낼 수 있다 - 받아 본 사람은
    어느 쪽이 맞는지 알 수 없다.
    """

    from app import app_info

    ready = found["readiness"]

    lines = [
        f"{app_info.NAME} Beta Release Report",
        "",
        f"버전       {found['version']}",
        f"확인 시점  {found['checked_at']}",
        f"설치본     {found['summary']['installations']}벌",
        "",
        f"Readiness  O {ready['passed']} · X {ready['failed']} "
        f"· ? {ready['unknown']}",
    ]

    for row in ready["checks"]:
        lines.append(f"  {row['mark']} {row['label']} - {row['detail']}")

    lines += ["", "Flow"]

    for row in found["funnel"]:
        lines.append(f"  {_pad(row['label'], 12)}{row['count']}")

    if found["cautions"]:
        lines += ["", "주의"]
        lines += [f"  - {line}" for line in found["cautions"]]

    return "\n".join(lines)


def build(snapshot: dict = None) -> dict:
    """
    밖으로 내보낼 한 장. 스냅샷이 낸 것만 옮긴다.

    snapshot을 주지 않으면 beta_snapshot에게 물어본다 - 화면과 같은
    한 벌을 보게 하기 위해서다.
    """

    from app.services import beta_snapshot

    found = snapshot if snapshot is not None else beta_snapshot.build()

    ready = found["readiness"]

    report = {
        "version": found["version"],
        "checked_at": found["taken_at"],
        "summary": {
            "installations": found["installations"],
        },
        "readiness": {
            "passed": ready["passed"],
            "failed": ready["failed"],
            "unknown": ready["unknown"],
            "checks": [
                {"group": row["group"], "label": row["label"],
                 "mark": MARKS[row["ok"]], "detail": row["detail"]}
                for row in ready["checks"]
            ],
        },
        "funnel": [{"label": row["label"], "count": row["count"]}
                   for row in found["flow"]],
        # 주의는 두 곳에서 온다 - 그때그때 나온 것과, 이 표가 무엇이
        # 아닌지를 밝히는 말. 둘 다 밖으로 나가야 한다.
        "cautions": list(found.get("warnings") or []) + [ready["caution"]],
    }

    report["report"] = _text(report)

    return report
