"""
Sprint181 - 막혔을 때 스스로 알아볼 수 있게 (Epic 59, Phase 4).

Sprint180이 "지금 어디에 있는가"를 만들었다. 그런데 막힌 사람에게
필요한 것은 그 한 줄이 아니라 셋이다.

    무엇이 문제인가       problems
    어떻게 하면 되는가    suggestions
    안 되면 무엇을 보내나  contact_text

새로 판정하지 않는다
--------------------
전부 이미 나온 답을 옮긴다.

    onboarding_state   지금 어디에 있는가, 무엇이 걸렸는가
    beta_telemetry     마지막에 무엇에 걸렸는가
    beta_feedback      보낼 것 한 덩이

여기서 문제를 새로 찾아내면, 화면이 말하는 문제와 실제로 막는 것이
달라진다. 그때 사람은 있지도 않은 것을 고치려 든다.

무엇이 여기 있는 것인가
-----------------------
해결 방법(HOW)뿐이다. 그것은 판정이 아니라 안내문이다 - 같은 상태에
같은 말을 한다.

문의 글에 지금 막힌 것을 함께 넣는다
------------------------------------
따로 적게 하면 사람은 "안 돼요"라고만 보낸다. 그 글에는 개인의 것이
들어가지 않는다 - beta_feedback이 이미 그런 것을 담지 않고, 문제
문장은 final_check·output_check가 만든 것이라 경로가 없다. 그 사실은
테스트가 상태마다 확인한다.
"""

from app.services import onboarding_state

# 상태마다 무엇을 하면 되는가. 판정이 아니라 안내문이다.
#
# 첫 줄은 onboarding_state가 이미 말한 "다음에 할 일"과 같은 방향을
# 가리켜야 한다 - 두 화면이 다른 것을 시키면 사람은 둘 다 안 믿는다.
HOW = {
    onboarding_state.FIRST_RUN: [
        "화면 위의 '내 자료 폴더 선택'을 눌러 그림과 목소리가 든 "
        "폴더를 고르십시오.",
        "그 폴더 아래에 images / voices 폴더가 있어야 합니다.",
    ],
    onboarding_state.WORKSPACE_REQUIRED: [
        "'내 자료 폴더 선택'을 눌러 폴더를 다시 고르십시오.",
        "폴더를 옮기셨다면 새 자리로 다시 골라 주십시오.",
    ],
    onboarding_state.SCRIPT_REQUIRED: [
        "대본 생성 방식을 고르고 요청문을 만들어 채팅창에 붙여넣으십시오.",
        "받은 답 전체를 복사해 '가져오기' 칸에 붙여넣으십시오.",
    ],
    onboarding_state.SCRIPT_CHECK_REQUIRED: [
        "아래 문제를 채팅창에 그대로 말하고 대본을 다시 받으십시오.",
        "고친 대본을 다시 붙여넣고 '대본 품질 확인'을 눌러 보십시오.",
    ],
    onboarding_state.ASSET_REQUIRED: [
        "아래에 적힌 Scene의 그림이나 목소리를 내 자료 폴더에 넣으십시오.",
        "파일 이름에 그 장면의 낱말을 넣으면 걸립니다"
        " (예: 무릎 스트레칭.png).",
        "목소리는 번호로 찾습니다 (예: scene3.wav).",
    ],
    onboarding_state.REVIEW_REQUIRED: [
        "막는 것은 아닙니다. 보고 넘어가실지 고치실지 정하십시오.",
        "다른 파일을 쓰고 싶으시면 그 장면에서 직접 고르실 수 있습니다.",
    ],
    onboarding_state.READY: [
        "'영상 만들기'를 누르시면 됩니다.",
        "만드는 동안 창을 닫으셔도 계속됩니다.",
    ],
    onboarding_state.RENDERING: [
        "끝날 때까지 기다려 주십시오.",
        "몇 분 걸립니다. 창을 닫으셔도 계속됩니다.",
    ],
    onboarding_state.COMPLETED: [
        "'결과 보기'에서 만들어진 영상을 확인하십시오.",
        "영상은 내 것 폴더의 output 아래에 있습니다.",
    ],
    onboarding_state.FAILED: [
        "아래에 적힌 것이 결과에서 빠진 부분입니다.",
        "그 장면의 자료를 고치고 다시 만들어 보십시오.",
        "그래도 안 되면 아래 글을 복사해 보내 주십시오.",
    ],
}


def _contact(status: str, problems: list) -> str:
    """
    보내실 글. 지금 막힌 것까지 함께 넣는다.

    판번호·사용 흐름은 beta_feedback이 짓는다 - 여기서 다시 지으면
    받아 보는 글의 모양이 두 가지가 된다.
    """

    from app import app_info
    from app.services import beta_feedback

    lines = [beta_feedback.report(), "", "지금 막힌 곳:", status]

    if problems:
        lines += ["", "화면이 말하는 문제:"] + list(problems)

    lines += ["", f"보내실 곳: {app_info.CONTACT}"]

    return "\n".join(lines)


def build(store_path: str, project_path: str = None) -> dict:
    """
    지금 무엇이 문제이고 어떻게 하면 되는가. 읽기만 한다.

    상태와 문제는 onboarding_state가 낸 그대로다 - 여기서 다시 세면
    진행 표시와 문제 해결이 서로 다른 이야기를 한다.
    """

    from app.services import beta_telemetry

    found = onboarding_state.build(store_path, project_path)

    status = found["state"]
    problems = list(found.get("reasons") or [])
    usage = beta_telemetry.summary()

    return {
        "status": status,
        "title": found["title"],
        "message": found["message"],
        "problems": problems,
        "suggestions": list(HOW[status]),
        "last_error_kind": usage.get("last_error_kind"),
        "steps": found.get("steps") or [],
        "contact_text": _contact(status, problems),
    }
