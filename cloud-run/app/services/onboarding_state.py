"""
Sprint180 - 지금 어디에서 막혔는가 (Epic 59, Phase 3).

처음 켠 사람은 화면에 있는 것들이 무엇을 뜻하는지 모른다. 자료 준비,
최종 확인, 출력 검사가 각각 제 이야기를 하는데, 그 셋을 이어 붙여
"그래서 지금 무엇을 해야 하는가"로 만드는 일은 사람이 해야 했다.

새로 판정하지 않는다
--------------------
이 파일이 지키는 가장 중요한 것이 그것이다. 여기 있는 것은 이어
붙이는 순서뿐이고, 답은 전부 이미 있는 서비스가 낸다.

    free_workspace.status      내 자료 폴더를 골랐는가
    studio_review.state        대본·이미지·음성·영상이 있는가
    script_quality_check       그 대본이 쓸 만한가
    final_check                지금 누르면 되는가
    output_check               나온 것이 쓸 만한가
    studio_jobs                지금 돌고 있는가

여기서 새 규칙을 하나라도 만들면, 화면이 "준비됨"이라는데 버튼을
누르면 막히는 일이 생긴다. 그때 사람은 둘 중 무엇을 믿어야 할지
모른다 - 그리고 대개 화면을 믿는다.

읽기만 한다
-----------
상태를 물어봤다고 이미지가 생기거나 렌더가 시작되면, 사람은 화면을
여는 것조차 조심스러워진다.

보는 차례
---------
    1. 지금 돌고 있는가          RENDERING
    2. 영상이 나왔는가           COMPLETED / REVIEW_REQUIRED / FAILED
    3. 폴더를 골랐는가           FIRST_RUN / WORKSPACE_REQUIRED
    4. 대본이 있는가             SCRIPT_REQUIRED
    5. 그 대본이 쓸 만한가       SCRIPT_CHECK_REQUIRED
    6. 지금 누르면 되는가        ASSET_REQUIRED / REVIEW_REQUIRED / READY

둘째가 셋째보다 앞이다 - 다 만든 사람에게 "폴더를 고르십시오"라고
할 수는 없다.
"""

FIRST_RUN = "FIRST_RUN"
WORKSPACE_REQUIRED = "WORKSPACE_REQUIRED"
SCRIPT_REQUIRED = "SCRIPT_REQUIRED"
SCRIPT_CHECK_REQUIRED = "SCRIPT_CHECK_REQUIRED"
ASSET_REQUIRED = "ASSET_REQUIRED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
READY = "READY"
RENDERING = "RENDERING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

# 화면이 그리는 여섯 줄. 이름과 차례를 여기서 한 번만 정한다.
STEPS = (
    ("workspace", "자료 연결"),
    ("script", "대본 준비"),
    ("image", "이미지 준비"),
    ("voice", "음성 준비"),
    ("video", "영상 제작"),
    ("output", "결과 확인"),
)

# 상태마다 무엇을 말하고 무엇을 누르게 할 것인가.
#
# (제목, 할 말, 다음에 할 일, 이어서 갈 수 있는가)
#
# 이어서 갈 수 있다는 것은 "누를 버튼이 있다"는 뜻이다. 막힌 자리는
# 버튼이 아니라 해결 방법을 보여 준다 - 누를 수 없는 버튼을 띄우면
# 사람은 그것을 누르고 아무 일도 안 일어나는 것을 본다.
SAYS = {
    FIRST_RUN: (
        "시작해 봅시다",
        "아직 아무것도 없습니다. 내 자료 폴더부터 고르십시오.",
        "내 자료 폴더 선택",
        False,
    ),
    WORKSPACE_REQUIRED: (
        "내 자료 폴더가 필요합니다",
        "그림과 목소리를 어디서 가져올지 아직 정하지 않았습니다.",
        "내 자료 폴더 선택",
        False,
    ),
    SCRIPT_REQUIRED: (
        "대본이 필요합니다",
        "채팅창에서 받은 대본을 붙여넣거나 직접 작성하십시오.",
        "대본 붙여넣기",
        False,
    ),
    SCRIPT_CHECK_REQUIRED: (
        "대본을 고쳐야 합니다",
        "지금 대본으로는 영상을 끝까지 만들 수 없습니다.",
        "대본 고치기",
        False,
    ),
    ASSET_REQUIRED: (
        "자료가 부족합니다",
        "빠진 그림이나 목소리가 있습니다. 폴더에 넣고 다시 확인하십시오.",
        "부족한 자료 보기",
        False,
    ),
    REVIEW_REQUIRED: (
        "확인할 것이 있습니다",
        "막지는 않습니다. 보고 넘어갈지 고치실지 정하십시오.",
        "검토 화면 이동",
        True,
    ),
    READY: (
        "만들 수 있습니다",
        "막는 것이 없습니다.",
        "영상 만들기",
        True,
    ),
    RENDERING: (
        "만드는 중입니다",
        "끝날 때까지 기다려 주십시오. 창을 닫아도 계속됩니다.",
        "진행 상황 보기",
        False,
    ),
    COMPLETED: (
        "영상이 나왔습니다",
        "결과를 확인하십시오.",
        "결과 보기",
        True,
    ),
    FAILED: (
        "결과에 문제가 있습니다",
        "만들어진 것에 빠진 부분이 있습니다.",
        "문제 보기",
        False,
    ),
}


def _running(project_path) -> bool:
    """
    지금 이 프로젝트를 만들고 있는가.

    작업 목록이 아는 것을 그대로 본다 - 여기서 다시 세지 않는다.
    """

    import os

    from app.services import studio_jobs

    wanted = os.path.basename((project_path or "").rstrip("\\/"))

    if not wanted:
        return False

    return any(
        job.get("state") == "running"
        and job.get("project_id") == wanted
        and job.get("kind") != "upload"
        for job in studio_jobs.recent(50)
    )


def _quality(project_path: str) -> dict:
    """
    적혀 있는 대본이 쓸 만한가.

    붙여넣기 전에 보던 그 검사에 물어본다 - 여기서 다시 세면 두
    자리가 다른 말을 한다.
    """

    from app.services import script_quality_check, studio_review

    try:
        script = studio_review._load_script(project_path)
    except Exception:
        return {"state": script_quality_check.NEEDS_WORK,
                "reasons": ["대본을 읽지 못했습니다."]}

    return script_quality_check.check(script)


def _steps(chosen: bool, done: dict, finished: bool) -> list:
    """여섯 줄. 이미 나온 답을 옮기기만 한다."""

    from app.services import studio_review

    made = {
        "workspace": chosen,
        "script": bool(done.get(studio_review.SCRIPT)),
        "image": bool(done.get(studio_review.IMAGE)),
        "voice": bool(done.get(studio_review.VOICE)),
        "video": bool(done.get(studio_review.VIDEO)),
        "output": finished,
    }

    return [{"key": key, "label": label, "done": made[key]}
            for key, label in STEPS]


def _said(state: str, reasons: list, steps: list, extra: dict) -> dict:
    title, message, action, can = SAYS[state]

    return {
        "state": state,
        "title": title,
        "message": message,
        "next_action": action,
        "can_continue": can,
        "reasons": reasons,
        "steps": steps,
        **extra,
    }


def build(store_path: str, project_path: str = None) -> dict:
    """
    지금 어디에 있는가. 읽기만 한다.

    store_path     내 자료 폴더를 적어 둔 자리
    project_path   보고 있는 프로젝트. 없으면 아직 아무것도 없는 것
    """

    from app.services import (
        final_check, free_workspace, local_library, output_check,
        studio_review,
    )

    chosen = bool(free_workspace.remembered(store_path).get("root"))

    # Sprint214 - 기억과 준비는 다른 것이다.
    #
    # remembered는 "폴더를 한 번 정하면 기억한다"는 편의다. 라이브러리를
    # 훑을 때 root를 안 주면 쓰는 기본값이고, 주면 쳐다보지도 않는다.
    #
    # 훑은 결과는 프로젝트 안에 남는다(local_library.json). 제작이
    # 기대는 것은 그쪽이고, Sprint213이 그것을 증명했다 - 전역 기억이
    # 빈 채로 영상이 끝까지 나왔다. 그런데 화면은 계속 "폴더를
    # 고르십시오"라고 했다. 같은 상태를 둘이 다르게 말한 것이다.
    #
    # 그래서 프로젝트가 제 자료 목록을 갖고 있으면 그 걸음은 끝난
    # 것으로 본다. 새 기준을 만드는 것이 아니라 local_library가 이미
    # 아는 사실을 읽는다 - load는 없으면 빈 것을 주고, 그것이 곧
    # "훑은 적이 없다"는 뜻이라고 그 docstring이 말한다.
    #
    # 여기서 기억을 채우지는 않는다. 사람이 고른 적이 없기 때문이다.
    if not chosen and project_path:
        chosen = bool(local_library.load(project_path).get("items"))

    if not project_path:
        state = WORKSPACE_REQUIRED if not chosen else SCRIPT_REQUIRED

        if not chosen:
            state = FIRST_RUN

        return _said(state, [], _steps(chosen, {}, False), {})

    review = studio_review.state(project_path)
    done = review.get("done") or {}
    scenes = review.get("scenes") or []

    # 다 만든 사람에게 "폴더를 고르십시오"라고 할 수는 없다.
    if _running(project_path):
        return _said(RENDERING, [], _steps(chosen, done, False), {})

    if done.get(studio_review.VIDEO):
        result = output_check.build(project_path, scenes)
        told = [issue.get("message") or "" for issue in
                (result.get("issues") or [])]

        state = {
            output_check.READY: COMPLETED,
            output_check.REVIEW: REVIEW_REQUIRED,
            output_check.FAILED: FAILED,
        }[result["state"]]

        return _said(state, told,
                     _steps(chosen, done, result["state"] ==
                            output_check.READY),
                     {"output": result})

    if not chosen:
        state = FIRST_RUN if not done.get(studio_review.SCRIPT) \
            else WORKSPACE_REQUIRED

        return _said(state, [], _steps(chosen, done, False), {})

    if not done.get(studio_review.SCRIPT):
        return _said(SCRIPT_REQUIRED, [], _steps(chosen, done, False), {})

    from app.services import script_quality_check

    quality = _quality(project_path)

    if quality["state"] != script_quality_check.READY:
        return _said(SCRIPT_CHECK_REQUIRED, quality["reasons"],
                     _steps(chosen, done, False), {})

    final = final_check.build(project_path, scenes)

    state = {
        free_workspace.READY: READY,
        free_workspace.REVIEW: REVIEW_REQUIRED,
        free_workspace.BLOCKED: ASSET_REQUIRED,
    }[final["state"]]

    told = list(final.get("problems") or []) + list(final.get("warnings")
                                                    or [])

    return _said(state, told, _steps(chosen, done, False),
                 {"final_check": final})
