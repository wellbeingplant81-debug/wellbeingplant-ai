"""
Sprint191 - 지금 내보낼 수 있는 상태인가 (Epic 59, Phase 14).

체크마크는 지어내면 안 된다
---------------------------
"O 무료 제작 흐름"이라고 찍어 놓고 그 근거가 없으면, 그 화면은
사람을 안심시키는 그림일 뿐이다. 그래서 여기 있는 줄은 전부 지금
이 자리에서 실제로 확인할 수 있는 사실이다.

    실행파일        묶인 프로그램으로 돌고 있는가
    데이터 분리     내 것이 프로그램 폴더 밖에 있는가
    무료 제작 흐름  대본까지 간 기록이 있는가
    렌더 완료       끝까지 간 기록이 있는가
    진단 정보       판번호를 담아 답하는가
    피드백 자리     그 폴더가 있는가

셋째와 넷째가 중요하다. "기능이 있다"가 아니라 "실제로 그렇게 된
기록이 있다"이다 - 우리가 말할 수 있는 것은 그것뿐이다.

여섯째와 다섯째는 약한 검사다. 폴더가 있다는 것과 답이 온다는 것을
볼 뿐이고, 그 이상을 확인하지 않았으므로 detail에 그렇게 적는다.

모르는 것은 모른다고 한다
-------------------------
테스트 결과 파일은 이 저장소에 없다. X로 찍으면 "실패했다"로 읽히고
O로 찍으면 거짓이다. 그래서 셋째 값(None)을 쓴다.

다 통과해도 "준비 완료"라고 하지 않는다
---------------------------------------
여섯 줄이 전부 O여도 그것은 이 여섯 가지가 확인됐다는 뜻이지 내보내도
된다는 뜻이 아니다. caution이 그 말을 직접 한다.
"""

import os

# 이 표가 무엇이 아닌지. payload가 직접 들고 다닌다.
CAUTION = (
    "여기 있는 것은 지금 확인된 여섯 가지뿐입니다. 전부 O여도 "
    "내보내도 된다는 뜻은 아닙니다."
)


def test_report_path():
    """
    테스트 결과를 적어 둔 파일. 이 저장소에는 아직 없다.

    자리를 함수로 둔 것은 생기면 그때 여기만 고치면 되게 하기
    위해서다 - 없는 파일을 있는 척 만들지 않는다.
    """

    return None


def _test_report() -> dict:
    """
    적어 둔 테스트 결과. 판정하지 않고 읽은 그대로 옮긴다.

    없으면 모른다고 한다 - X는 "실패했다"로 읽힌다.
    """

    path = test_report_path()

    if not path or not os.path.isfile(path):
        return {"ok": None, "detail": "적어 둔 테스트 결과가 없습니다."}

    try:
        with open(path, encoding="utf-8") as f:
            said = f.read().strip().splitlines()[-1]
    except OSError:
        return {"ok": None, "detail": "테스트 결과를 읽지 못했습니다."}

    # 우리가 다시 판정하지 않는다 - 적힌 말을 그대로 읽는다.
    return {"ok": said.startswith("OK"), "detail": said[:120]}


def build(summary: dict = None) -> dict:
    """
    지금 확인되는 것들. 읽기만 한다.

    통과 기준을 새로 만들지 않는다 - 각 줄은 이미 있는 자리에
    물어본 답이다.

    Sprint192 - 이미 만들어 둔 summary를 받을 수 있다. 한 장 안에서
    여럿이 볼 때 각자 다시 읽으면 그 사이에 기록이 바뀌고, 숫자가
    서로 어긋난다.
    """

    from app import app_info, runtime_paths
    from app.services import beta_summary, diagnostic_report, media_tools

    if summary is None:
        summary = beta_summary.build()

    funnel = {row["key"]: row["count"] for row in summary["funnel"]["steps"]}

    home = runtime_paths.home()
    program = runtime_paths.program_dir()

    separated = not os.path.normcase(os.path.abspath(home)).startswith(
        os.path.normcase(os.path.abspath(program)))

    report = diagnostic_report.build(runtime_paths.workflow_root())
    diagnostic_ok = report.get("version") == app_info.VERSION

    feedback_there = os.path.isdir(runtime_paths.feedback_root())

    script_ready = funnel.get("script_ready", 0)
    finished = summary["finished"]

    checks = [
        {"group": "배포", "key": "executable", "label": "실행파일",
         "ok": runtime_paths.is_frozen(),
         "detail": "묶인 프로그램으로 돌고 있는지 봅니다."},
        {"group": "배포", "key": "data_separated", "label": "사용자 데이터 분리",
         "ok": separated,
         "detail": "내 것이 프로그램 폴더 밖에 있는지 봅니다."},
        {"group": "제작", "key": "free_flow", "label": "무료 제작 흐름",
         "ok": script_ready > 0,
         "detail": f"대본까지 간 기록 {script_ready}벌."},
        {"group": "제작", "key": "render_done", "label": "렌더 완료 확인",
         "ok": finished > 0,
         "detail": f"끝까지 간 기록 {finished}벌."},
        {"group": "운영", "key": "diagnostic", "label": "진단 정보",
         "ok": diagnostic_ok,
         "detail": "판번호를 담아 답하는지만 봅니다."},
        {"group": "운영", "key": "feedback_place", "label": "피드백 자리",
         "ok": feedback_there,
         "detail": "적어 둘 폴더가 있는지만 봅니다."},
    ]

    told = _test_report()

    checks.append({"group": "운영", "key": "test_report",
                   "label": "테스트 결과", "ok": told["ok"],
                   "detail": told["detail"]})

    warnings = list(summary.get("notes") or [])

    for name in media_tools.missing():
        warnings.append(f"{name} 를 찾지 못했습니다.")

    if not report["environment"].get("music"):
        warnings.append("배경 음악이 없어 영상을 만들 수 없습니다.")

    return {
        "version": app_info.VERSION,
        "checks": checks,
        "warnings": warnings,
        "caution": CAUTION,
        "passed": sum(1 for row in checks if row["ok"] is True),
        "failed": sum(1 for row in checks if row["ok"] is False),
        "unknown": sum(1 for row in checks if row["ok"] is None),
    }
