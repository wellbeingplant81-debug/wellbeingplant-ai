"""
Sprint162 - 누르기 전에 마지막으로 본다 (Epic 57, Phase 13).

Sprint160·161이 자료 준비 상태를 만들었다. 그런데 그것과 "지금 렌더를
누르면 되는가"는 다른 물음이다.

    자료 준비   내 자료로 만들 수 있는가         free_workspace.preparation
    산출물      scene1.png·scene1.wav이 있는가   scene_order.render_problems

둘은 갈린다
-----------
내 자료가 다 있어도 아직 만들지 않았으면 렌더는 막힌다 - Sprint145의
검사가 그렇게 한다. 그때 화면이 "준비 완료"라고만 하면 사람은 버튼을
누르고 400을 본다.

반대로 내 자료가 없어도 예전에 만들어 둔 산출물이 있으면 렌더는 돈다.

그래서 둘 다 본다. 해야 할 일이 다르기 때문이다.

    자료가 없다     폴더에 파일을 넣어라
    산출물이 없다   이미지·음성을 만들어라

여기서 판정하지 않는다
----------------------
두 판정 모두 이미 있는 것을 그대로 읽는다. 여기서 다시 재면 화면이
"가능"이라고 한 것을 서버가 거절하는 날이 온다 - 막는 일은 예전부터
있던 그 검사가 한다.

검토는 막지 않는다
------------------
Sprint156부터의 규칙이다. 같은 그림을 여러 Scene에 쓰는 것도, 낱말
하나로 걸린 것도 사람이 일부러 그랬을 수 있다. 말하되 막지 않는다.
"""

import os

from app.services import free_workspace


def _asset_problems(prepared: dict) -> list:
    """자료가 모자란 Scene들. 사람이 읽을 말로."""

    problems = []

    for row in prepared["scenes"]:
        if row["state"] != free_workspace.BLOCKED:
            continue

        for reason in row["reasons"]:
            label = {
                "script": "대본", "image": "이미지", "voice": "음성",
            }.get(reason)

            if label:
                problems.append(f"Scene {row['scene']} {label} 없음")

    return problems


def _warnings(prepared: dict) -> list:
    """막지는 않지만 사람이 봐야 하는 것들."""

    labels = {
        "weak": "약한 매칭", "shared": "같은 파일 사용",
        "override_gone": "정한 파일 없어짐",
    }

    found = []

    for row in prepared["scenes"]:
        if row["state"] != free_workspace.REVIEW:
            continue

        why = " · ".join(labels.get(r, r) for r in row["reasons"])

        found.append(f"Scene {row['scene']} 검토 필요 - {why}")

    return found


def _confirmed(prepared: dict) -> list:
    """
    사람이 보고 괜찮다고 한 것들.

    무엇을 왜 확인했는지 함께 적는다 - "확인함"만으로는 무엇을 봤는지
    알 수 없다.
    """

    found = []

    for row in prepared["scenes"]:
        decision = row.get("confirmed")

        if not decision:
            continue

        found.append({
            "scene": row["scene"],
            # 사람이 확인한 그 파일이다. 지금 자리에 있는 파일 이름을
            # 쓰면 안 된다 - 만들고 나면 scene1.png이 되어, 무엇을
            # 봤는지가 사라진다.
            "file": os.path.basename(decision.get("path") or "") or None,
            "reasons": decision.get("reasons") or [],
            "confirmed_at": decision.get("confirmed_at"),
            "confirmed_by": decision.get("confirmed_by"),
        })

    return found


def _counts(prepared: dict, key: str) -> dict:
    """그 자리가 준비된 Scene 수 / 전체."""

    return {
        "ready": sum(
            1 for row in prepared["scenes"] if row[key].get("ready")
        ),
        "total": prepared["total"],
    }


def build(project_path: str, scenes: list) -> dict:
    """
    지금 누르면 되는가. 읽고 말하기만 한다.

    돌려주는 것:

        state       READY / REVIEW / BLOCKED
        can_render  버튼을 열어도 되는가
        problems    막는 것들(자료 + 산출물)
        warnings    막지 않지만 봐야 하는 것들
        confirmed   사람이 보고 괜찮다고 한 것들
        assets      자료 쪽 판정 그대로
        outputs     지금 렌더를 걸면 걸리는 것(기존 검사 그대로)
    """

    from app.services import scene_order

    prepared = free_workspace.preparation(project_path, scenes)

    # 막는 일은 이 검사가 한다. 여기서 다시 재지 않는다.
    outputs = scene_order.render_problems(project_path, scenes) if scenes \
        else []

    problems = _asset_problems(prepared) + list(outputs)

    if problems or not prepared["total"]:
        state = free_workspace.BLOCKED
    elif prepared["counts"][free_workspace.REVIEW]:
        state = free_workspace.REVIEW
    else:
        state = free_workspace.READY

    return {
        "state": state,
        "can_render": state != free_workspace.BLOCKED,
        "total": prepared["total"],
        "images": _counts(prepared, "image"),
        "voices": _counts(prepared, "voice"),
        "review": prepared["counts"][free_workspace.REVIEW],
        "problems": problems,
        "warnings": _warnings(prepared),
        "confirmed": _confirmed(prepared),
        # 무엇을 해야 하는지 갈라 볼 수 있게 둘을 따로 둔다.
        "assets": {
            "state": prepared["state"],
            "counts": prepared["counts"],
        },
        "outputs": list(outputs),
    }
