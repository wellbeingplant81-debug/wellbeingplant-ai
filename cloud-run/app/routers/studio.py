"""
Sprint80 - AI Video Studio UI.

엔진은 건드리지 않는다. 이 라우터는 두 가지만 한다 - 화면을 내려 주고,
디스크에 이미 있는 산출물을 읽어 돌려준다. 생성은 기존
factory_service.generate_short_video를 그대로 부른다.

프로젝트 경로는 반드시 project_service.resolve_project_path를 거친다.
Sprint65에서 만든 것이고, 요청 하나로 output 밖을 가리키는 것을 막는
유일한 지점이다. 여기서 새로 만들지 않는다.
"""

import os

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app import config, settings
from app.services import (
    oauth_manager, project_service, studio_jobs, studio_regeneration,
    studio_replay, studio_service, studio_upload, studio_workflow,
)
from app.tools import asset_dataset


router = APIRouter(prefix="/studio", tags=["studio"])


_STATIC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
)

_PAGE = os.path.join(_STATIC, "studio.html")
_REPLAY_PAGE = os.path.join(_STATIC, "replay.html")
_QUEUE_PAGE = os.path.join(_STATIC, "queue.html")

# Sprint84 - 사람이 내린 결정만 여기 쌓인다. 프로젝트 디렉터리
# 밖이라 생산 산출물은 손대지 않는다.
_WORKFLOW_STORE = None


class GenerateRequest(BaseModel):
    topic: str
    channel: str = "wellbeing"
    # Sprint107 - 붙여넣기/직접 작성으로 미리 만들어 둔 프로젝트가
    # 있으면 그것으로 만든다. 없으면(기본값) 예전과 똑같이 새로 만든다.
    #
    # Sprint232 - Optional 이어야 한다. pydantic v2 에서 `str = None` 은
    # "없어도 되는 문자열"이 아니라 "문자열인데 기본값이 None" 이다.
    # 키를 빼면 지나가지만 null 을 실어 보내면 422 로 막힌다 - 화면은
    # 늘 후자를 한다.
    project_id: Optional[str] = None
    # Sprint218 - 어느 갈래로 눌렀는가. 보내지 않으면 예전과 똑같다
    # (직접 고르기 화면의 [영상 생성]이 그렇다) - 기존 동작을 바꾸지
    # 않기 위해 기본값을 None으로 둔다.
    #
    # Sprint232 - 그 "보내지 않으면"이 실제로는 닫혀 있었다. 화면은
    # `creationMode || null` 로 늘 null 을 실어 보내고, pydantic v2 는
    # 명시된 null 을 str 로 받지 않는다. 아래 검사에 `is None` 가지가
    # 있는데 요청이 거기까지 닿지 못했다.
    creation_mode: Optional[str] = None
    # 비용이 발생할 수 있다는 안내를 사람이 확인했는가. 유료 API를
    # 부를 수 있는 갈래에서는 이것이 없으면 시작하지 않는다.
    cost_ack: bool = False


class ChatImportRequest(BaseModel):
    # 사용자가 붙여넣은 것 그대로. 우리가 손대지 않는다.
    raw: str
    # 제목이 없는 붙여넣기를 메울 때만 쓴다.
    topic: str = ""


class ImportProjectRequest(ChatImportRequest):
    channel: str = "wellbeing"
    # import(붙여넣기) 또는 manual(직접 작성). 읽는 방법은 같고
    # 기록으로만 남는다.
    source: str = "import"


class StagePlanRequest(BaseModel):
    # {단계: 입력방식}. 고르지 않은 단계는 계획에 들어가지 않는다.
    selections: dict
    # Sprint139 - {단계: Provider 이름}. maker에서 고른 것이다.
    # 비어 있으면 예전처럼 그 단계의 첫 Provider(현재 엔진)로 센다.
    providers: dict = {}


class RegenerateRequest(BaseModel):
    # None이면 엔진이 실패 scene 전부를 알아서 고른다. 목록을 주면
    # 그 안으로 좁혀진다 - 통과한 scene을 넣어도 정책이 걸러낸다.
    scenes: list = None


def _project_path(project_id: str) -> str:
    try:
        return project_service.resolve_project_path(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="프로젝트가 없습니다.")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def studio_page():
    """
    Studio 화면.

    Sprint173 - 판번호를 여기서 채운다. 화면 파일에 적어 두면 그 자리가
    다음 판에 뒤처진다 - 실제로 "Studio v1"이라고 적힌 채로 여러 판이
    지나갔다. 값은 app_info 하나에서만 온다.
    """

    from app import app_info

    try:
        with open(_PAGE, "r", encoding="utf-8") as f:
            page = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="studio.html이 없습니다.")

    page = page.replace(app_info.PAGE_TOKEN, app_info.label())
    page = page.replace(app_info.CONTACT_TOKEN, app_info.CONTACT)

    # Sprint218 - 고른 테마를 <html data-theme>에 심는다.
    #
    # 자바스크립트가 켜진 뒤에 붙이면, 라이트를 고른 사람은 켤 때마다
    # 검은 화면이 한 번 번쩍이는 것을 본다(첫 그림은 :root 기본값인
    # 다크로 그려지기 때문이다). 서버는 이미 그 값을 알고 있으므로
    # 여기서 적어 두면 첫 그림부터 제 색이다.
    #
    # 모르는 값이 적혀 있어도 화면은 뜬다 - settings.theme()이 다크로
    # 되돌린다.
    page = page.replace(settings.THEME_TOKEN, settings.theme())

    return HTMLResponse(page)


# ── Sprint218 - 화면 테마 (Epic 62) ──────────────────────────────────
#
# 새 설정 저장 체계를 만들지 않는다. app.settings가 이미 %APPDATA% 아래
# settings.json을 들고 있고 "없는 것만 채운다"는 규칙까지 지킨다.


class ThemeRequest(BaseModel):
    theme: str


@router.get("/api/settings")
def settings_view():
    """지금 설정. 화면이 테마 고르는 칸을 그릴 때 읽는다."""

    return {
        "theme": settings.theme(),
        "themes": [
            {"key": key, "label": settings.THEME_LABELS[key]}
            for key in settings.THEMES
        ],
        "open_browser": settings.load().get(settings.OPEN_BROWSER, True),
        "path": settings.path(),
    }


@router.put("/api/settings/theme")
def settings_theme(request: ThemeRequest):
    """
    고른 테마를 적는다.

    모르는 값은 막는다 - 조회(theme())는 오타를 다크로 되돌려 주지만,
    적는 자리에서까지 조용히 받아 주면 사람은 "골랐는데 안 바뀐다"를
    겪는다.
    """

    if not settings.is_theme(request.theme):
        raise HTTPException(
            status_code=400,
            detail=f"알 수 없는 테마입니다: {request.theme!r}. "
                   f"사용 가능한 값: {list(settings.THEMES)}",
        )

    try:
        settings.save({settings.THEME: request.theme})
    except Exception as exc:
        # 적지 못했으면 그렇다고 말한다. "저장했습니다"라고 해 놓고
        # 다음에 없으면 안 된다.
        raise HTTPException(
            status_code=500,
            detail=f"테마를 저장하지 못했습니다: {exc}",
        )

    return {"theme": settings.theme()}


# ── Sprint218 - 제작 방식과 과금 확인 ────────────────────────────────


@router.get("/api/production/creation-modes")
def creation_modes_view():
    """
    사람이 고를 두 갈래와, 각 갈래에서 돈이 들 수 있는가.

    비용 안내문을 화면에 적어 두지 않는다 - 어느 단계가 API를 부르는지는
    등록된 Provider에 따라 달라지고, 화면이 그것을 다시 세면 어느 날
    엔진과 다른 말을 한다.
    """

    from app.production import creation_modes

    return {"modes": creation_modes.all_as_dict()}


@router.get("/api/about")
def about():
    """
    Sprint174 - 지금 무엇을 쓰고 있는가. 화면의 [정보 복사]가 읽는다.

    왜 필요한가
    -----------
    막힌 사람에게 "어느 판이고 무엇이 없습니까"를 물으면, 그 사람은
    창을 뒤져 옮겨 적어야 한다. 곤란해진 다음이라 대개 안 한다.

    붙여 넣을 글도 여기서 짓는다
    ----------------------------
    화면이 제 나름대로 조립하면 받아 보는 글의 모양이 사람마다 달라
    무엇이 빠졌는지 알 수 없다.

    지어내지 않는다 - 전부 지금 이 프로그램이 실제로 보고 있는 값이다.
    """

    from app import app_info, runtime_paths
    from app.services import beta_telemetry, media_tools

    tools = media_tools.available()

    music_where = os.path.join(runtime_paths.music_root(),
                               runtime_paths.MUSIC_INBOX)
    music_ready = runtime_paths._has_music(runtime_paths.music_root())

    found = {
        "name": app_info.NAME,
        "version": app_info.VERSION,
        "build": app_info.build_date(),
        "contact": app_info.CONTACT,
        "home": runtime_paths.home(),
        "tools": tools,
        "music": {"ready": music_ready, "where": music_where},
        "feedback": runtime_paths.feedback_root(),
        # Sprint175 - 어디까지 갔는가. 개인의 것은 들어 있지 않다 -
        # beta_telemetry가 애초에 그런 것을 적지 않는다.
        "usage": beta_telemetry.summary(),
        "usage_report": beta_telemetry.report(),
    }

    lines = [
        app_info.title(),
        f"내 것    {found['home']}",
    ]

    for name in (media_tools.FFMPEG, media_tools.FFPROBE):
        lines.append(f"{name:<8} {tools[name] or '없음'}")

    lines.append(f"배경음악 {'있음' if music_ready else '없음 · ' + music_where}")

    found["report"] = "\n".join(lines)

    return found


@router.get("/api/onboarding")
def onboarding(project_id: str = ""):
    """
    Sprint180 - 지금 어디에서 막혔는가.

    새로 판정하지 않는다. 이미 있는 서비스가 낸 답을 이어 붙인 것을
    그대로 내준다 - 여기서 다시 세면 화면이 "준비됨"이라는데 버튼을
    누르면 막히는 일이 생긴다.

    없는 프로젝트를 물어도 404를 던지지 않는다. 던지면 첫 화면이
    통째로 비어 버린다 - 그 화면이 바로 "무엇을 해야 하는가"를
    말해 줘야 하는 자리다.
    """

    from app.services import onboarding_state

    path = None

    if project_id:
        # 다른 엔드포인트가 쓰는 그 자리를 그대로 쓴다 - 여기서만
        # 다른 길로 찾으면 화면이 보는 프로젝트와 어긋난다.
        try:
            path = _project_path(project_id)
        except Exception:
            path = None

    return onboarding_state.build(_workspace_store(), path)


@router.get("/api/diagnostic-report")
def diagnostic_report_package(project_id: str = ""):
    """
    Sprint182 - 문의할 때 그대로 보낼 한 덩이.

    새로 판정하지 않는다. troubleshooting이 낸 답에 판번호와 갖춰진
    것을 얹어 내준다.

    도구는 있다/없다만 담는다 - 이 글은 밖으로 나가므로 어디 있는지를
    담으면 남의 PC 구조가 함께 나간다. [정보 복사]와 다른 자리다.
    """

    from app.services import diagnostic_report

    path = None

    if project_id:
        try:
            path = _project_path(project_id)
        except Exception:
            path = None

    return diagnostic_report.build(_workspace_store(), path)


@router.get("/api/beta-action-progress")
def beta_action_progress():
    """
    Sprint187 - 도움말이 가리킨 걸음에 닿았는가.

    새 기록을 적지 않는다. 도움말을 언제 열었는지 모르므로 "도움말
    때문에 넘어갔다"고 말할 수 없다 - 답에 그 사실(caution)을 함께
    담아 화면이 '효과'로 읽지 않게 한다.
    """

    from app.services import beta_action_tracking

    return beta_action_tracking.build()


@router.get("/api/beta-actions")
def beta_actions_card():
    """
    Sprint186 - 그래서 어느 안내를 열면 되는가.

    해결 방법을 새로 만들지 않는다. 이미 있는 안내가 어디 있는지를
    가리키기만 한다.

    가리키는 것은 '막힌 단계'가 아니라 '그 다음 걸음'이다 - 폴더를
    이미 고른 사람에게 폴더 안내를 열어 주면 자기가 이미 한 일을
    다시 읽게 된다.
    """

    from app.services import beta_actions

    return beta_actions.build()


@router.get("/api/beta-insights")
def beta_insights_card():
    """
    Sprint185 - 무엇부터 고칠 것인가.

    세지 않는다. beta_dashboard가 낸 숫자만 읽는다 - 두 자리가 각각
    세면 화면마다 다른 숫자가 뜬다.

    겹치면 하나를 고르지 않고, 기록이 적으면 적다고 말한다 - 두
    벌짜리에서 "가장 많이 막힌 곳"을 단정하면 그것은 자료가 아니라
    우연이다.
    """

    from app.services import beta_insights

    return beta_insights.build()


@router.get("/api/beta-package-validation")
def beta_package_validation_card():
    """
    Sprint201 - 받은 폴더에 있어야 할 것이 있는가.

    만들지 않는다. 없는 자리를 여기서 만들어 주면 그것은 검증이 아니라
    설치이고, 그 다음부터는 무엇이 원래 있던 것인지 알 수 없다.

    켜 봤다고 말하지도 않는다 - 두 번 눌러 화면이 뜨는지는 사람이
    봐야 하고, 그 사실을 답의 note가 직접 말한다.
    """

    from app.services import beta_package_validation

    return beta_package_validation.build()


@router.get("/api/beta-release-candidate")
def beta_release_candidate_card(project_id: str = ""):
    """
    Sprint200 - 처음 쓰는 사람의 여덟 걸음.

    가 봤다고 말하지 않는다. 기록을 읽을 뿐이라 확인된 것과 아직 모르는
    것만 적는다 - "통과" 같은 말은 여기서 만들지 않는다.

    없는 프로젝트를 물어도 404를 던지지 않는다. onboarding_state가
    같은 이유로 그렇게 한다 - 첫 화면이 통째로 비면 안 된다.
    """

    from app.services import beta_release_candidate

    path = None

    if project_id:
        try:
            path = _project_path(project_id)
        except Exception:
            path = None

    return beta_release_candidate.build(_workspace_store(), path)


@router.get("/api/beta-release-gate")
def beta_release_gate_card():
    """
    Sprint199 - 배포를 정하려는 사람이 보는 한 장.

    앞의 자리들이 낸 답을 모아 놓기만 한다. 문을 여닫지 않는다 -
    "배포 가능" 같은 말은 여기서 만들지 않고, 그러면 안 되는 이유는
    beta_readiness의 caution이 그대로 실려 말한다.
    """

    from app.services import beta_release_gate

    return beta_release_gate.build()


@router.get("/api/beta-release-report")
def beta_release_report_card():
    """
    Sprint193 - 밖으로 내보낼 한 장.

    스냅샷이 낸 것만 옮긴다. 여기서 세거나 고르지 않는다 - 그러면
    이 글과 화면이 다른 말을 하고, 받아 본 사람은 어느 쪽이 맞는지
    알 수 없다.
    """

    from app.services import beta_release_report

    return beta_release_report.build()


@router.get("/api/beta-snapshot")
def beta_snapshot_card():
    """
    Sprint192 - 지금을 한 장으로.

    저장하지 않는다. 읽은 것을 그대로 내줄 뿐이고, 그 사실을 답이
    직접 말한다 - 안 그러면 사람이 나중에 그 파일을 찾는다.
    """

    from app.services import beta_snapshot

    return beta_snapshot.build()


@router.get("/api/beta-readiness")
def beta_readiness_card():
    """
    Sprint191 - 지금 확인되는 것들.

    통과 기준을 새로 만들지 않는다. 각 줄은 이미 있는 자리에 물어본
    답이고, 모르는 것은 O도 X도 아닌 '모름'으로 낸다.

    전부 O여도 "내보내도 된다"는 뜻이 아니다 - 그 말을 답이 직접
    한다(caution).
    """

    from app.services import beta_readiness

    return beta_readiness.build()


@router.get("/api/beta-summary")
def beta_summary_card():
    """
    Sprint190 - 베타 운영 정보를 한 장으로.

    새로 세지 않는다. 기록을 한 번만 읽고 그 하나를 다섯에게 나눠
    준다 - 각자 읽으면 한 화면 안에서 숫자가 서로 어긋난다.
    """

    from app.services import beta_summary

    return beta_summary.build()


@router.get("/api/beta-feedback-insights")
def beta_feedback_insights_card():
    """
    Sprint189 - 단계마다 무엇이 붙는가.

    '단계별 의견 건수'는 만들지 않는다. 피드백 글에는 어느 단계에서
    썼는지가 적히지 않고, 글과 기록을 짝지으면 그것이 곧 사용자
    식별이다. 대신 실제로 있는 것(그 단계에서 멈춘 설치본 수, 그
    단계에서 난 오류)을 붙이고, 그 차이를 답이 직접 말한다.
    """

    from app.services import beta_feedback_loop

    return beta_feedback_loop.build()


@router.get("/api/beta-funnel")
def beta_funnel_card():
    """
    Sprint188 - 몇 벌이 시작해서 몇 벌이 끝냈는가.

    세지 않는다. beta_dashboard가 낸 숫자를 늘어놓고 뺄셈만 한다.

    앞 칸보다 큰 칸이 나와도 다듬지 않는다 - 사건이 칸마다 따로
    적히기 때문이고, 다듬으면 그것은 자료가 아니라 그림이다.
    """

    from app.services import beta_funnel

    return beta_funnel.build()


@router.get("/api/beta-dashboard")
def beta_dashboard_panel():
    """
    Sprint184 - 베타가 어디에서 멈추는지.

    세기만 한다. 기록은 설치본마다 하나이므로, 받아 온 것을
    <관측 기록>/collected/ 에 넣어야 여럿이 세어진다 - 몇 벌을 보고
    센 것인지(installations)를 함께 내주는 이유다.

    로그인은 없다. 이 서버는 127.0.0.1에만 열려 있고, 그것이 지금
    유일한 경계다 - "관리자 전용"이라고 부르지 않는다.
    """

    from app.services import beta_dashboard

    return beta_dashboard.build()


@router.get("/api/first-run-guide")
def first_run_guide_card(project_id: str = ""):
    """
    Sprint183 - 처음 쓰는 사람의 여섯 걸음.

    새로 판정하지 않는다. onboarding_state가 낸 답을 처음 쓰는 사람이
    읽을 수 있는 낱말로 옮긴 것을 그대로 내준다.
    """

    from app.services import first_run_guide

    path = None

    if project_id:
        try:
            path = _project_path(project_id)
        except Exception:
            path = None

    return first_run_guide.build(_workspace_store(), path)


@router.get("/api/troubleshooting")
def troubleshooting_center(project_id: str = ""):
    """
    Sprint181 - 무엇이 문제이고 어떻게 하면 되는가.

    새로 찾아내지 않는다. onboarding_state가 낸 답을 사람이 읽을 수
    있는 모양으로 옮긴 것을 그대로 내준다 - 여기서 다시 세면 진행
    표시와 문제 해결이 서로 다른 이야기를 한다.
    """

    from app.services import troubleshooting

    path = None

    if project_id:
        try:
            path = _project_path(project_id)
        except Exception:
            path = None

    return troubleshooting.build(_workspace_store(), path)


@router.get("/api/beta-feedback")
def beta_feedback_package():
    """
    Sprint177 - 보내 주실 것 한 덩이.

    화면의 [베타 피드백 복사]가 읽는다. 개인의 것은 들어 있지 않다 -
    beta_telemetry가 애초에 그런 것을 적지 않고, 꾸러미는 그 안에 있는
    것만 옮긴다.

    붙여 넣을 글도 여기서 짓는다. 화면이 제 나름대로 조립하면 받아
    보는 글의 모양이 사람마다 달라진다.
    """

    from app.services import beta_feedback

    found = beta_feedback.package()
    found["report"] = beta_feedback.report()

    return found


def _workflow_store() -> str:
    # Sprint92 - 경로 정의는 studio_upload 한 곳에만 둔다. 파이프라인도
    # 같은 것을 본다.
    return studio_upload.default_store_path()


def _running_projects() -> set:
    """지금 생성/재생성이 돌고 있는 프로젝트."""

    return {
        job["project_id"]
        for job in studio_jobs.recent(50)
        if job.get("state") == "running" and job.get("project_id")
        and job.get("kind") != "upload"
    }


def _upload_started() -> dict:
    """지금 도는 업로드 작업이 언제 시작했나. {project_id: 시각}"""

    return {
        job["project_id"]: job.get("started_at")
        for job in studio_jobs.recent(50)
        if job.get("state") == "running" and job.get("project_id")
        and job.get("kind") == "upload"
    }


def _uploading_projects() -> set:
    """지금 올리고 있는 프로젝트. 저장하지 않고 도는 작업에서 읽는다."""

    return {
        job["project_id"]
        for job in studio_jobs.recent(50)
        if job.get("state") == "running" and job.get("project_id")
        and job.get("kind") == "upload"
    }


@router.get("/queue", response_class=HTMLResponse)
def queue_page():
    """Production Queue 화면."""

    try:
        with open(_QUEUE_PAGE, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="queue.html이 없습니다.")


@router.get("/api/queue")
def queue(status: str = "all"):
    rows = studio_workflow.queue(
        project_service.OUTPUT_ROOT, _workflow_store(), _running_projects(),
        _uploading_projects(), _upload_started(),
    )

    try:
        filtered = studio_workflow.filter_rows(rows, status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    counts = {key: 0 for key in studio_workflow.STATUSES}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    return {
        "status": status,
        "labels": studio_workflow.LABELS,
        "counts": counts,
        "total": len(rows),
        "rows": filtered,
        # Sprint92 - 업로드 경로가 생겼다. 다만 플래그가 꺼져 있으면
        # 실제로는 올라가지 않으므로, 화면이 그 사실을 그대로 말할 수
        # 있게 두 가지를 따로 알려준다.
        "upload_available": True,
        "upload_enabled": bool(config.ENABLE_YOUTUBE_UPLOAD),
    }


@router.post("/api/projects/{project_id}/approve")
def approve(project_id: str):
    """승인은 workflow 상태만 바꾼다. 엔진 산출물은 그대로다."""

    _project_path(project_id)

    try:
        return studio_workflow.approve(project_id, _workflow_store())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Sprint105 - 제작 방식 화면.
#
# 등록소를 여기서 따로 만든다. 전역 default_registry()에 올리면
# app.main을 import하는 것만으로 등록이 일어나고, "등록은 명시적으로
# 부를 때만"이라는 Sprint103의 계약이 깨진다.
_production_registry = None


def _registry():
    global _production_registry

    if _production_registry is None:
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        _production_registry = StageProviderRegistry()
        bootstrap.register_current_providers(_production_registry)

    return _production_registry


@router.get("/api/production/modes")
def production_modes_view():
    """제작 방식 목록과 각 방식의 예상 비용.

    비용을 지어내지 않는다 - Provider가 단가를 모르면 그 단계는
    unknown으로 오고, 화면이 그것을 그대로 보여준다."""

    from app.production import production_modes as modes
    from app.production import source_modes, stages
    from app.production.production_plan import build_automatic_plan

    registry = _registry()
    rows = []

    for mode in modes.PRODUCTION_MODES:
        policy = modes.policy_for(mode)
        row = {
            "mode": mode,
            "label": modes.LABELS[mode],
            "description": modes.DESCRIPTIONS[mode],
            "user_chooses_per_stage": policy.user_chooses_per_stage,
            "calls_api": modes.calls_api(mode),
            "auto_regenerate": policy.auto_regenerate,
            "cost": None,
            "missing_stages": [],
        }

        if not policy.user_chooses_per_stage:
            plan = build_automatic_plan(mode, registry)
            row["cost"] = plan.estimate_cost(registry=registry).as_dict()
            row["missing_stages"] = [
                stages.LABELS[s] for s in plan.missing_stages()
            ]

        rows.append(row)

    return {
        "modes": rows,
        "current_engine_mode": modes.CURRENT_ENGINE_MODE,
        "stage_labels": stages.LABELS,
    }


def _provider_availability(provider):
    """
    이 Provider를 지금 쓸 수 있는가.

    Provider가 스스로 말하게 한다 - 라우터가 환경변수를 뒤지기
    시작하면 판정이 두 곳에 생긴다. 아무 말도 없으면 쓸 수 있는
    것으로 본다(current·import 계열이 그렇다).
    """

    if getattr(provider, "coming_soon", False):
        return False, "아직 붙지 않았습니다."

    if hasattr(provider, "availability"):
        return provider.availability()

    return True, ""


def _voice_engine_facts():
    """
    음성은 지금 실제로 무엇이 도는가.

    TTS_PROVIDER를 바꾸면 파이프라인 전체가 그것으로 돈다
    (app/providers/tts_provider.py). 화면이 Google이라고만 적어 두면
    설정을 바꾼 사람에게 거짓말을 하게 된다.
    """

    from app.providers import elevenlabs_provider

    if os.getenv("TTS_PROVIDER", "google").lower() != "elevenlabs":
        return ENGINE_FACTS["voice"]

    return {
        "name": "ElevenLabs",
        "model": elevenlabs_provider.model_id(),
        "calls_api": True,
    }


@router.get("/api/production/stages")
def production_stages_view():
    """단계마다 무엇을 고를 수 있고, 지금 누가 그것을 맡을 수 있는가."""

    from app.production import source_modes, stage_timing, stages

    registry = _registry()
    rows = []

    for stage in stages.STAGES:
        allowed = stages.allowed_source_modes(stage)
        rows.append({
            "stage": stage,
            "label": stages.LABELS[stage],
            "source_modes": list(allowed),
            "source_labels": {m: source_modes.LABELS[m] for m in allowed},
            # 그 방식을 맡을 Provider가 지금 있는가. 없으면 화면이
            # 고를 수는 있어도 만들 수 없다는 것을 말해야 한다.
            "providers": {
                mode: [p.name for p in registry.available(stage, mode)]
                for mode in allowed if mode != source_modes.NONE
            },
            # Sprint116 - 화면이 "품질 예상"을 지어내지 않도록 Provider가
            # 스스로 신고한 등급을 그대로 내보낸다. 지금은 전부
            # standard다 - 등급을 매길 상대가 아직 없기 때문이고,
            # 그것이 사실이므로 화면도 그렇게 말해야 한다.
            "provider_quality": {
                p.name: p.capabilities.quality_tier
                for mode in allowed if mode != source_modes.NONE
                for p in registry.available(stage, mode)
            },
            # Sprint117 - 무슨 AI인지 화면이 말할 수 있도록.
            "engine": (_voice_engine_facts() if stage == "voice"
                       else ENGINE_FACTS[stage]),
            # Sprint124 - 고를 수 있는 것 전부. 아직 붙지 않은 자리도
            # 숨기지 않고 왜 못 쓰는지 함께 준다.
            "provider_list": [
                {
                    "name": p.name,
                    "display_name": p.capabilities.label,
                    "vendor": p.capabilities.vendor,
                    "quality_tier": p.capabilities.quality_tier,
                    "estimated_cost": p.capabilities.estimated_cost,
                    "source_modes": list(
                        p.capabilities.supported_source_modes),
                    "coming_soon": bool(getattr(p, "coming_soon", False)),
                    # Sprint125 - 설정이 됐는가. 안 됐으면 왜인지도
                    # 함께 준다 - 화면이 지어내지 않게.
                    "available": _provider_availability(p)[0],
                    "unavailable_reason": _provider_availability(p)[1],
                    "required_settings": list(
                        p.capabilities.required_settings),
                    # Sprint138 - 환경변수로 담을 수 없는 인증 방식.
                    # 화면이 "필요 없음"이라고 잘못 말하지 않게 한다.
                    "authentication": p.capabilities.authentication,
                    # Sprint140 - 이 엔진이 안에서 함께 쓰는 곳들.
                    # 화면이 추가로 필요한 인증을 말할 수 있게 한다.
                    "secondary_providers": [
                        {
                            "name": s.name,
                            "display_name": s.label,
                            "vendor": s.vendor,
                            "authentication": s.authentication,
                            "required_settings": list(s.required_settings),
                            "note": s.description,
                        }
                        for s in p.capabilities.secondary_providers
                    ],
                    "note": p.capabilities.description,
                }
                for p in registry.for_stage(stage)
            ],
            "seconds_if_generated": stage_timing.seconds_for(stage),
            "note": stages.NOTES.get(stage, ""),
        })

    return {
        "stages": rows,
        "fixed_seconds": stage_timing.FIXED_SECONDS,
        "observed_total_seconds": stage_timing.OBSERVED_TOTAL_SECONDS,
        "sample_size": stage_timing.SAMPLE_SIZE,
        "measured_at": stage_timing.MEASURED_AT,
    }


# Sprint117 - 단계마다 실제로 도는 것.
#
# 화면이 "AI 생성"이라고만 적던 자리에 이 이름이 들어간다. 모델
# 문자열은 서비스 함수 안에 인라인으로 박혀 있어서 import할 상수가
# 없다 - 그래서 여기 적고, 그것이 실제 코드와 어긋나지 않는지는
# tests/test_studio_ux3.py가 잠근다. 모델을 바꾸면 그 테스트가 먼저
# 깨진다.
#
# calls_api는 돈이 나가는가이다. 메타데이터는 규칙 기반이라 호출이
# 없고(Sprint94), BGM은 assets/music/의 mp3를 고르는 것이라 역시 없다.
# 계획의 api_stages는 generate면 전부 세므로 그 둘까지 포함하는데,
# 화면은 실제로 나가는 것만 센다.
ENGINE_FACTS = {
    "script": {
        "name": "Gemini 2.5 Pro",
        "model": "gemini-2.5-pro",
        "calls_api": True,
    },
    "image": {
        "name": "Imagen 4.0",
        "model": "imagen-4.0-generate-001",
        "calls_api": True,
    },
    "voice": {
        "name": "Google TTS Chirp3-HD",
        "model": "ko-KR-Chirp3-HD-Aoede",
        "calls_api": True,
    },
    "metadata": {
        "name": "규칙 기반 생성기",
        "model": None,
        "calls_api": False,
    },
    "music": {
        "name": "로컬 BGM",
        "model": None,
        "calls_api": False,
    },
}


def _known_provider(stage: str, name: str, registry) -> bool:
    """
    그 단계가 이 이름을 아는가.

    Sprint139 - maker의 계획과 Review의 저장이 같은 규칙을 써야 한다.
    두 자리가 다른 이름을 받아 주면 고른 것이 도중에 바뀐다.

    받아 줄 이름은 두 층에서 온다.

        엔진이 아는 이름   provider_selection.WIRED - 지금 실제로 도는 것
        등록소의 이름      app.production - 아직 안 붙은 자리들.
                           골라 두면 만들 때 정직하게 거절한다

    둘은 겹치지 않는다 - 등록소의 "google_tts"는 모델을 직접 부르는
    다른 자리이고, 엔진의 "google"은 지금 도는 경로다.
    """

    from app.services import provider_selection

    if name in provider_selection.WIRED[stage]:
        return True

    try:
        registry.get(stage, name)
    except ValueError:
        return False

    return True


def _unknown_provider_error(stage: str, name: str, registry):
    from app.services import provider_selection

    known = list(provider_selection.WIRED[stage]) + [
        p.name for p in registry.for_stage(stage)
    ]

    return HTTPException(
        status_code=400,
        detail=(
            f"{stage} 단계가 모르는 Provider입니다: {name}. "
            f"사용 가능한 값: {provider_selection.CURRENT}, "
            f"{', '.join(sorted(set(known)))}"
        ),
    )


@router.post("/api/production/plan")
def production_plan_view(request: StagePlanRequest):
    """
    고른 것으로 계획을 만들어 비용·시간·API 사용을 돌려준다.

    실행하지 않는다 - 계획만 만든다.
    """

    from app.production import production_modes, source_modes, stages
    from app.production.production_plan import (
        PlanError, ProductionPlan, StageSelection,
    )
    from app.services import provider_selection

    registry = _registry()
    plan = ProductionPlan(mode=production_modes.ASSISTED)

    # 고른 Provider가 어느 단계 것인지부터 본다. 모르는 단계를 조용히
    # 흘리면 고른 대로 만들어지지 않는다.
    try:
        for stage in (request.providers or {}):
            stages.require_stage(stage)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        for stage, mode in (request.selections or {}).items():
            stages.require_stage(stage)
            source_modes.require_source_mode(mode)

            provider = None
            if source_modes.calls_api(mode):
                chosen = registry.available(stage, mode)
                provider = chosen[0].name if chosen else None

                # Sprint139 - maker에서 고른 것이 있으면 그것으로 센다.
                # 없으면 위에서 고른 첫 Provider 그대로다.
                wanted = (request.providers or {}).get(stage)

                if wanted and wanted != provider_selection.CURRENT:
                    if not _known_provider(stage, wanted, registry):
                        raise _unknown_provider_error(
                            stage, wanted, registry)

                    provider = wanted

            plan.select(StageSelection(
                stage=stage, source_mode=mode, provider=provider,
                # 화면이 아직 내용을 보내지 않는다 - 계획만 세우는
                # 단계라 있는 셈 친다.
                payload="(선택함)" if mode in (
                    source_modes.IMPORT, source_modes.MANUAL) else None,
            ))
    except (PlanError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = plan.as_dict()
    result["cost"] = plan.estimate_cost(registry=registry).as_dict()
    result["missing_stages"] = [
        stages.LABELS[s] for s in plan.missing_stages()
    ]
    result["stages_without_provider"] = [
        stages.LABELS[s.stage]
        for s in plan.selections.values()
        if s.calls_api and not s.provider
    ]

    return result


@router.post("/api/production/images")
async def production_images(
    project_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """
    직접 만든 이미지를 프로젝트에 놓는다.

    받은 파일을 임시로 내려놓고 Provider에게 넘긴다 - 놓는 규칙과
    scene 수 검증은 Provider가 한다. 화면 전용 경로를 따로 만들지
    않는다.
    """

    import shutil
    import tempfile

    from app.production.providers.image_import import ImageImportError
    from app.production.stage_request import StageRequest

    path = _project_path(project_id)

    # 대본은 Resolver가 읽고 검증한다(Sprint106) - 새 읽기 경로를
    # 만들지 않는다. scene 수를 알아야 몇 장이 필요한지 판정할 수 있다.
    from app.steps.step01_script_resolve import (
        ScriptResolveError, load_prepared,
    )

    try:
        scenes = load_prepared(path)["scenes"]
    except ScriptResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    staging = tempfile.mkdtemp()

    try:
        given = []
        for upload in files:
            target = os.path.join(staging, os.path.basename(upload.filename))
            with open(target, "wb") as f:
                shutil.copyfileobj(upload.file, f)
            given.append(target)

        provider = _registry().get("image", "image_import")

        try:
            result = provider.accept_manual(
                given, StageRequest(project_path=path, scenes=scenes),
            )
        except ImageImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {
        "scene_count": result["scene_count"],
        "image_count": result["image_count"],
        "warnings": result["warnings"],
        "scenes": [
            {
                "scene": scene["scene"],
                "url": (
                    f"/studio/api/projects/{project_id}"
                    f"/media/scene?scene={scene['scene']}"
                ),
            }
            for scene in result["scenes"]
        ],
    }


@router.post("/api/production/voice")
async def production_voice(
    project_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """
    직접 만든 음성을 프로젝트에 놓는다.

    받은 파일을 임시로 내려놓고 Provider에게 넘긴다 - 놓는 규칙과
    길이 검증은 Provider가 한다. 화면 전용 경로를 따로 만들지 않는다
    (Sprint110 이미지와 같은 모양이다).
    """

    import shutil
    import tempfile

    from app.production.providers.voice_import import VoiceImportError
    from app.production.stage_request import StageRequest
    from app.steps.step01_script_resolve import (
        ScriptResolveError, load_prepared,
    )

    path = _project_path(project_id)

    # 대본은 Resolver가 읽고 검증한다(Sprint106) - 새 읽기 경로를
    # 만들지 않는다. scene 수와 나레이션을 알아야 몇 개가 필요한지,
    # 몇 초짜리가 될지 판정할 수 있다.
    try:
        scenes = load_prepared(path)["scenes"]
    except ScriptResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    staging = tempfile.mkdtemp()

    try:
        given = []
        for upload in files:
            target = os.path.join(staging, os.path.basename(upload.filename))
            with open(target, "wb") as f:
                shutil.copyfileobj(upload.file, f)
            given.append(target)

        provider = _registry().get("voice", "voice_import")

        try:
            result = provider.accept_manual(
                given, StageRequest(project_path=path, scenes=scenes),
            )
        except VoiceImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {
        "scene_count": result["scene_count"],
        "voice_count": result["voice_count"],
        "measured_seconds": result["measured_seconds"],
        "expected_seconds": result["expected_seconds"],
        "warnings": result["warnings"],
        # 전체 나레이션 하나로 들어온 경우다 - scene별 파일이 없다.
        "whole": (
            {
                "name": os.path.basename(result["voice_path"]),
                "seconds": result["measured_seconds"],
                "url": f"/studio/api/projects/{project_id}/media/voice",
            }
            if result["voice_path"] else None
        ),
        "voices": [
            {
                "scene": voice["scene"],
                "name": voice["name"],
                "seconds": voice["seconds"],
                "url": (
                    f"/studio/api/projects/{project_id}"
                    f"/media/voice_scene?scene={voice['scene']}"
                ),
            }
            for voice in result["voices"]
        ],
    }


class ScriptPromptRequest(BaseModel):
    # Sprint154 - 무엇에 대한 영상인가. 나머지는 비우면 엔진 기본값이다.
    #
    # Sprint178 - 직접 입력은 물어볼 창이 없으므로 주제도 없다.
    topic: str = ""
    target_duration: int = 0
    scene_count: int = 0
    style: str = ""
    audience: str = ""
    # Sprint178 - 어느 채팅창에 넣을 글인가. 비우면 Sprint154 그대로다.
    provider: str = ""


@router.post("/api/script-prompt")
def script_prompt(request: ScriptPromptRequest):
    """
    Sprint154 - 채팅창에 붙여넣을 요청문을 만든다.
    Sprint178 - 어느 창인지는 고른 사람이 정한다(script_provider).

    부르지 않는다. 글자를 만들 뿐이다 - 우리가 대신 물어봐 주면 그
    순간 돈이 들고, 그러면 무료 모드가 아니다.
    """

    from app.services import script_provider

    try:
        return script_provider.build(
            request.provider,
            topic=request.topic,
            target_duration=request.target_duration,
            scene_count=request.scene_count,
            style=request.style,
            audience=request.audience,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ScriptCheckRequest(BaseModel):
    # Sprint179 - 붙여넣기 전에 읽어 볼 것 그대로.
    raw: str = ""


@router.post("/api/script-check")
def script_check(request: ScriptCheckRequest):
    """
    Sprint179 - 붙여넣기 전에 대본을 읽어 본다.

    고치지 않는다. 읽고 말할 뿐이다 - 우리가 대신 고치면 사람은
    무엇이 잘못됐는지 영영 모르고, 다음에도 같은 자리에서 걸린다.

    못 읽는 대본도 400으로 던지지 않는다. 던지면 화면은 "실패"라고만
    하고, 무엇을 고쳐야 하는지는 사라진다.
    """

    from app.production.chat_script_parser import ChatImportError
    from app.production.providers.chat_import import ChatImportScriptProvider
    from app.production.stage_request import StageRequest
    from app.services import script_quality_check

    # 읽는 일은 여기서 한다. app.production 은 이 라우터만 들인다 -
    # 서비스가 들이면 test_production_architecture가 막는다(Sprint166이
    # 같은 자리에서 걸렸다).
    script, refused = None, None

    if (request.raw or "").strip():
        try:
            script = ChatImportScriptProvider().import_content(
                request.raw, StageRequest(topic=""))
        except ChatImportError as exc:
            refused = str(exc)
        except Exception as exc:
            refused = f"대본을 읽지 못했습니다: {exc}"

    return script_quality_check.check(script, refused=refused)


@router.post("/api/production/import")
def production_import(request: ChatImportRequest):
    """
    붙여넣은 대본을 읽어 무엇이 들어왔는지 보여준다.

    여기서 프로젝트를 만들지 않는다. 파이프라인의 step01이 기존
    script.json을 읽는 분기 없이 항상 새로 만들기 때문에, 지금 저장해
    두어도 영상 생성이 시작되는 순간 덮어써진다 - 그 연결은 파이프라인을
    고쳐야 하고 이번 스프린트는 그것을 금지한다.

    읽기와 검증은 실제 Provider가 한다. 화면 전용 파서를 따로 만들지
    않는다.
    """

    from app.production.chat_script_parser import ChatImportError
    from app.production.stage_request import StageRequest

    provider = _registry().get("script", "chat_import")

    try:
        script = provider.import_content(
            request.raw, StageRequest(topic=request.topic),
        )
    except ChatImportError as exc:
        # 사람이 읽고 고칠 수 있는 문장이 그대로 화면에 가야 한다.
        raise HTTPException(status_code=400, detail=str(exc))

    # Sprint108 - 만들기 전에 무엇이 나올지. 재기만 하고 대본은
    # 손대지 않는다.
    from app.production import script_forecast

    return {
        "title": script["title"],
        "hook": script["hook"],
        "forecast": script_forecast.forecast(script, _registry()),
        "scene_count": len(script["scenes"]),
        "scenes": [
            {
                "scene": scene["scene"],
                "narration": scene["narration"],
                "image_prompt": scene.get("image_prompt", ""),
            }
            for scene in script["scenes"]
        ],
        "script": script["script"],
    }


@router.post("/api/production/project")
def production_create_project(request: ImportProjectRequest):
    """
    붙여넣은 대본으로 프로젝트를 만든다.

    여기서 영상을 만들지 않는다 - 만드는 것은 기존 "영상 생성"
    버튼이고, 그 버튼이 이 project_id를 들고 간다. Generate 경로를
    새로 만들지 않는다.
    """

    from app.production.chat_script_parser import ChatImportError
    from app.production.imported_project import create_from_script
    from app.production.stage_request import StageRequest

    provider = _registry().get("script", "chat_import")

    try:
        script = provider.import_content(
            request.raw, StageRequest(topic=request.topic),
        )
    except ChatImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    from app.services import beta_telemetry

    try:
        made = create_from_script(
            script,
            request.topic or script["title"],
            request.channel,
            request.source,
        )
    except ValueError as exc:
        beta_telemetry.note_failure(exc)

        raise HTTPException(status_code=400, detail=str(exc))

    # Sprint175 - 대본이 들어왔다는 사실만. 대본 내용도 제목도 적지
    # 않는다.
    beta_telemetry.note(beta_telemetry.SCRIPT_READY,
                        once=made.get("project_id"))

    return made


@router.post("/api/projects/{project_id}/upload")
def upload(project_id: str):
    """
    Sprint92 - 승인된 프로젝트를 YouTube에 올린다.

    승인 여부는 studio_upload가 본다 - 여기서 다시 판정하지 않는다.
    승인되지 않았으면 작업은 정상으로 끝나고 outcome이 skipped로 온다.
    """

    from app.services import publish_gate

    path = _project_path(project_id)

    # Sprint149 - 올리기 전에 본다. 앞 관문에서 막히면 뒤쪽은 아예
    # 실행되지 않는다 - studio_upload가 플래그와 승인을 보는 것과
    # 같은 방식이고, 여기서는 그보다 앞선 사실을 본다.
    #
    # studio_upload도 승인을 다시 본다. 두 번 보는 것이 맞다 - 이
    # 자리는 화면이 부르는 입구일 뿐이고, 실제 안전장치는 그쪽이다.
    if not studio_upload.is_approved(project_id, _workflow_store()):
        raise HTTPException(
            status_code=400,
            detail="승인된 프로젝트만 올릴 수 있습니다.",
        )

    problems = publish_gate.problems(path)

    if problems:
        raise HTTPException(status_code=400, detail=" · ".join(problems))

    job_id = studio_jobs.start_upload(project_id, path)

    return {"job_id": job_id}


@router.post("/api/projects/{project_id}/request-upload")
def request_upload(project_id: str):
    """
    Sprint148 - 올리겠다고 요청한다. 올리지는 않는다.

    Sprint147의 검사를 먼저 통과해야 한다 - 제목도 영상도 없는 것을
    큐에 올려 두면 승인하는 사람이 무엇을 승인하는지 알 수 없다.
    """

    from app.services import publish_gate

    path = _project_path(project_id)
    problems = publish_gate.problems(path)

    if problems:
        raise HTTPException(status_code=400, detail=" · ".join(problems))

    try:
        return studio_workflow.request_upload(project_id, _workflow_store())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/projects/{project_id}/retry-upload")
def retry_upload(project_id: str):
    """
    Sprint149 - 실패한 것을 다시 올려 달라고 한다.

    새 승인 체계를 만들지 않는다 - 이미 받아 둔 승인을 그대로 쓰고,
    지난 실패를 지난 일로 넘긴다. 결과 파일은 지우지 않는다.
    """

    _project_path(project_id)

    try:
        return studio_workflow.retry_upload(project_id, _workflow_store())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/projects/{project_id}/reject")
def reject(project_id: str, request: RejectRequest = None):
    """거절한다. 요청을 거두고 사유를 남긴다."""

    _project_path(project_id)

    try:
        return studio_workflow.reject(
            project_id, _workflow_store(),
            (request.reason if request else "") or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/projects/{project_id}/unapprove")
def unapprove(project_id: str):
    _project_path(project_id)

    try:
        studio_workflow.unapprove(project_id, _workflow_store())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True}


@router.get("/replay", response_class=HTMLResponse)
def replay_page():
    """Replay Viewer 화면."""

    try:
        with open(_REPLAY_PAGE, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="replay.html이 없습니다.")


@router.get("/api/replay")
def replay(rule: str = "baseline"):
    """축적된 데이터셋 전체를 규칙 하나로 되돌려 본다. 순수 읽기."""

    try:
        return studio_replay.replay_view(rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/projects/{project_id}/replay")
def project_replay(project_id: str, rule: str = "baseline"):
    try:
        return studio_replay.project_replay_view(
            _project_path(project_id), rule,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/projects")
def projects():
    return {"projects": studio_service.list_projects(
        project_service.OUTPUT_ROOT,
    )}


@router.get("/api/projects/{project_id}")
def project(project_id: str):
    return studio_service.project_detail(_project_path(project_id))


@router.get("/api/projects/{project_id}/media/{kind}")
def media(project_id: str, kind: str, scene: int = None):
    path = _project_path(project_id)

    try:
        target = studio_service.media_path(path, kind, scene)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="파일이 없습니다.")

    return FileResponse(target)


def _refuse_if_the_script_is_not_ready(project_id: str) -> None:
    """
    Sprint203 - 못 갈 것은 부르기 전에 막는다.

    문지기가 화면에만 있었다. 화면은 버튼을 감추지만 그 아래 API는
    누구에게나 열려 있었고, 그리로 들어오면 몇 초 뒤 개발자 문구로
    죽었다 - "scene 1: image_prompt 없음". 같은 프로그램이 같은
    상태를 두 가지로 말한 것이다.

    막는 기준은 계약이지 품질이 아니다
    ----------------------------------
    script_quality_check로 막으면 "9초로 짧습니다"처럼 렌더가 견디는
    것까지 막힌다. 그래서 렌더가 실제로 대괄호로 꺼내는 것만 본다 -
    어차피 죽었을 것을 더 일찍, 더 또렷하게 막을 뿐이다.

    하는 말은 이미 있는 말
    ----------------------
    새 문구를 지으면 화면과 API가 다른 낱말로 같은 것을 말하게 된다.
    script_quality_check가 만든 문장을 그대로 옮긴다.

    지어 넣지 않는다
    ----------------
    빠진 것을 여기서 채우면 그것은 더 이상 사용자가 준 대본이 아니다.
    """

    from app.services import onboarding_state, script_quality_check
    from app.steps import step01_script_resolve as resolver

    if not project_id:
        # AI가 대본을 쓰는 길. 아직 없는 대본을 미리 검사할 수 없다.
        return

    try:
        path = _project_path(project_id)
    except Exception:
        return

    if not os.path.isfile(resolver.script_path(path)):
        # 미리 놓인 대본을 쓰는 길이 아니다.
        return

    try:
        script = resolver.load_prepared(path)
    except resolver.ScriptResolveError:
        script = None

    if script is not None:
        return

    # 여기까지 왔다면 계약을 못 갖췄다. 무슨 말을 할지는 이미 있는
    # 자리에 물어본다.
    try:
        found = resolver._load(resolver.script_path(path))
    except Exception:
        found = {}

    quality = script_quality_check.check(found)

    said = onboarding_state.SAYS[onboarding_state.SCRIPT_CHECK_REQUIRED]

    raise HTTPException(status_code=400, detail={
        # Sprint204 - 이름표를 함께 보낸다.
        #
        # 화면이 "대본 고치기"라는 글자를 보고 무엇을 열지 정하면,
        # 문구가 바뀌는 날 조용히 틀린다. 새 판단이 아니라 이미 내린
        # 판단에 이름을 붙여 보내는 것이다.
        "state": onboarding_state.SCRIPT_CHECK_REQUIRED,
        "message": said[1],
        "reasons": quality.get("reasons") or [],
        "next_action": said[2],
    })


def _refuse_unconfirmed_cost(request: "GenerateRequest") -> None:
    """
    Sprint218 - 돈이 들 수 있는 갈래는 확인 없이 시작하지 않는다.

    이 검사가 서버에 있는 이유
    --------------------------
    화면의 confirm() 하나로 끝내면 그것은 연극이다. 창을 새로 열어
    같은 요청을 보내면 그냥 시작된다. 확인을 받았다는 사실이 요청에
    실려 와야 하고, 실려 오지 않으면 서버가 거절해야 한다.

    기존 [영상 생성]은 그대로 둔다
    ------------------------------
    creation_mode를 안 보내면 이 검사를 지나간다. 그 단추는 단계마다
    사람이 직접 Provider를 고른 뒤에 누르는 자리이고, 그 화면에는 이미
    예상 비용과 "API 3 Stages"가 카드로 떠 있다 - 고지 없이 시작되는
    자리가 아니다. 새로 생긴 [완전 자동으로 만들기]가 그 반대여서
    (아무것도 고르지 않고 한 번에 시작한다) 문이 필요한 것이다.
    """

    from app.production import creation_modes

    if request.creation_mode is None:
        return

    try:
        creation_modes.require_creation_mode(request.creation_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    policy = creation_modes.cost_policy_for(request.creation_mode)

    if not policy.requires_confirmation or request.cost_ack:
        return

    raise HTTPException(
        status_code=400,
        detail="비용이 발생할 수 있다는 안내를 확인하지 않으셨습니다. "
               f"{policy.reason} 화면의 안내에서 [확인하고 시작]을 "
               "누르면 시작합니다.",
    )


@router.post("/api/jobs")
def create_job(request: GenerateRequest):
    if not request.topic or not request.topic.strip():
        raise HTTPException(status_code=400, detail="주제를 입력하십시오.")

    # 확인을 안 받았으면 프로젝트도 작업도 만들지 않는다 - 취소는
    # "아무 일도 일어나지 않는다"여야 한다.
    _refuse_unconfirmed_cost(request)

    # Sprint203 - 못 갈 것은 여기서 막는다. 작업을 만들어 두고 몇 초
    # 뒤에 죽이면 큐에 죽을 것이 쌓이고, 사람은 무엇을 해야 하는지
    # 모른 채 기다린다.
    _refuse_if_the_script_is_not_ready(request.project_id)

    # Sprint107 - project_id가 오면 미리 만들어 둔 프로젝트로 만든다.
    # 없으면 예전과 똑같이 새 프로젝트를 만든다. 버튼도 엔드포인트도
    # 하나 그대로다.
    return {"job_id": studio_jobs.start(request.topic.strip(),
                                        request.channel,
                                        request.project_id,
                                        request.creation_mode)}


@router.get("/api/jobs/{job_id}")
def job(job_id: str, console_from: int = 0):
    result = studio_jobs.status(job_id, console_from)

    if not result.get("found"):
        raise HTTPException(status_code=404, detail="작업이 없습니다.")

    # 진행 단계는 디스크의 산출물로 판정한다. 로그 문구에 기대면
    # 파이프라인이 print를 바꿀 때마다 UI가 조용히 틀린다.
    #
    # 끝난 뒤에만 판정하면 생성 중에는 진행률을 전혀 못 보여 준다.
    # project_path는 생성 직후 로그 한 줄에서 얻는다 - 어디를 볼지만
    # 로그에서 얻고, 무엇이 끝났는지는 여전히 파일이 정한다.
    path = result.get("project_path")

    if not path and result.get("project_id"):
        path = os.path.join(
            project_service.OUTPUT_ROOT, result["project_id"],
        )

    result["stages"] = (
        studio_service.stage_progress(path) if path
        else studio_service.stage_progress("")
    )

    # Sprint176 - 결과는 여기서 적지 않는다.
    #
    # Sprint175는 여기서 적었다. 아무도 물어보지 않으면 아무것도 안
    # 적혔고, 창을 닫아 두고 기다린 사람의 렌더는 기록에 없었다.
    # 이제 만드는 실이 끝나는 자리(studio_jobs)에서 직접 적는다 -
    # 두 자리가 적으면 한 번 돈 렌더가 두 번으로 보인다.

    return result


# Sprint121 - 승인 기반 제작.
#
# 한 단계씩 만들고, 사람이 보고 승인하면 다음으로 간다. 여기서 하는
# 일은 studio_review를 부르는 것뿐이고, 그 아래는 전부 이미 있는
# 엔진이다. 마지막 Render는 생성 버튼이 쓰는 그 경로를 그대로 쓴다.


class ReviewScriptRequest(BaseModel):
    # 사람이 고친 대본 그대로. 우리가 손대지 않는다.
    data: dict
    # Sprint145 - 보여 줄 차례. {"order": [...], "deleted": [...]}
    #
    # 대본과 한 번에 오지만 한 파일에 섞이지 않는다 - 대본은
    # script.json, 차례는 timeline.json이다. 없으면 차례는 그대로 둔다.
    timeline: dict = None


class LibraryScanRequest(BaseModel):
    # Sprint150 - 훑을 폴더. 그 아래 images/videos/music/voice를 본다.
    #
    # Sprint152 - 비워 두면 정해 둔 내 자료 폴더를 쓴다. 프로젝트마다
    # 같은 경로를 다시 적게 만들지 않는다.
    root: str = ""


class SceneAssetRequest(BaseModel):
    # Sprint158 - 이 scene에 쓸 파일. 훑어 둔 목록에 있는 것이어야 한다.
    path: str


class WorkspaceRequest(BaseModel):
    # Sprint152 - 내 자료 폴더. 한 번 정하면 기억한다.
    root: str


class RejectRequest(BaseModel):
    # Sprint148 - 사람이 쓴 거절 사유. 비어 있어도 거절은 된다.
    reason: str = ""


class ReviewMetadataRequest(BaseModel):
    # Sprint147 - 사람이 고친 칸. publish_gate.EDITABLE에 있는 것만
    # 반영된다 - 나머지를 보내도 무시한다.
    metadata: dict


class ReviewProviderRequest(BaseModel):
    # {단계: Provider 이름}. 고르지 않은 단계는 그대로 둔다.
    providers: dict


@router.post("/api/review")
def review_create(request: GenerateRequest):
    """
    검토하며 만들 빈 프로젝트를 만든다.

    아무것도 생성하지 않는다 - 첫 단계는 사람이 누른 뒤에 돈다.
    프로젝트를 만드는 일은 기존 create_project를 그대로 쓴다.
    """

    if not request.topic or not request.topic.strip():
        raise HTTPException(status_code=400, detail="주제를 입력하십시오.")

    project = project_service.create_project(
        request.topic.strip(), request.channel,
    )

    return {"project_id": project["id"]}


def _review_length(path, state):
    """
    지금 영상이 몇 초짜리인가.

    음성이 생기기 전에는 대본 글자 수로 미루어 볼 수밖에 없고, 생긴
    뒤에는 잴 수 있다. 잴 수 있는데 미루어 보면 화면이 틀린 숫자를
    말하게 되므로 둘을 나눠서 준다.

    새 계산은 만들지 않는다 - 예상은 Duration Gate가 쓰는 그 estimator,
    실측은 Duration Optimizer가 쓰는 그 ffprobe 호출이다.

    Sprint143 - scene마다의 값도 함께 돌려준다. 예전에도 여기서 구하고
    있었는데 합만 남기고 버렸다.

        estimate_script_duration은 문자 그대로 scene별
        estimate_duration의 합이다. 그러니 scene별 값을 내보내는 것은
        새 계산이 아니라 버리던 것을 살리는 일이다.

    실측 목록은 render가 쓰는 그 값이기도 하다 - scene_timeline.
    build_timeline이 같은 get_audio_duration을 부르고 그 경계로 영상이
    만들어진다. 그래서 앞에서부터 더한 것이 영상 속 시작 시각이다.

    돌려주는 목록은 그때의 총합과 같은 종류다 - 실측이 있으면 실측,
    없으면 예상. 화면은 measured_seconds가 있는지로 둘을 가른다.
    """

    from app.services import audio_policy
    from app.services.duration_estimator import estimate_duration
    from app.services.duration_optimizer import get_audio_duration

    scenes = state.get("scenes") or []

    per_scene = [
        estimate_duration(scene.get("narration") or "") for scene in scenes
    ]
    estimated = sum(per_scene)

    measured = None
    if scenes and all(s.get("has_voice") for s in scenes):
        per_scene = [
            get_audio_duration(os.path.join(
                path, "audio", "scenes",
                audio_policy.scene_audio_filename(scene["scene"]),
            ))
            for scene in scenes
        ]
        measured = round(sum(per_scene), 2)

    return (
        round(estimated, 2),
        measured,
        [round(value, 2) for value in per_scene],
    )


def _review_metadata(path):
    """
    Render가 만든 publish_package.json. 없으면 None.

    여기서 만들지 않는다 - 메타데이터는 파이프라인이 영상을 만들면서
    쓰는 것이고, 그 전에는 없는 것이 사실이다.
    """

    from app.services import publish_gate

    package = publish_gate.package(path)

    if package is None:
        return None

    return {
        # Sprint147 - 화면이 보여 줄 것과 고칠 수 있는 것.
        #
        # 고칠 수 있는 셋(title·description·tags)과 만들어진 것들을
        # 한 자리에 담되, 무엇이 고칠 수 있는지는 publish_gate가
        # 정한다 - 화면이 따로 정하면 두 곳이 갈린다.
        "editable": list(publish_gate.EDITABLE),
        "tags": package.get("tags") or [],
        "category": package.get("category"),
        "category_id": package.get("category_id"),
        "thumbnail_text": package.get("thumbnail_text"),
        "privacy_status": package.get("privacy_status"),
        **{
        key: package.get(key)
        for key in ("title", "description", "hashtags", "playlist_title")
        },
    }


def _library_state(path: str) -> dict:
    """훑어 둔 내 PC 자료의 요약. 목록 전체는 보내지 않는다 - 화면이
    쓰는 것은 어느 폴더를 훑었는가와 몇 개인가뿐이다."""

    from app.services import local_library

    index = local_library.load(path)

    return {
        "root": index.get("root"),
        "counts": local_library.counts(index),
    }


@router.get("/api/review/{project_id}")
def review_state(project_id: str):
    """어디까지 왔는가. 순수 읽기다 - 산출물이 말한다."""

    from app.services import (
        local_library, provider_selection, publish_gate, scene_order,
        studio_review,
    )

    path = _project_path(project_id)
    state = studio_review.state(path)
    estimated, measured, scene_seconds = _review_length(path, state)

    return {
        "project_id": project_id,
        **state,
        # Sprint123 - 화면이 영상을 보여 주는 데 필요한 읽기값.
        # studio_review는 손대지 않는다.
        # Sprint126 - 이 프로젝트가 고른 Provider. 안 고른 것은
        # current로 온다.
        "providers": provider_selection.all_selected(path),
        "estimated_seconds": estimated,
        "measured_seconds": measured,
        # Sprint143 - scene마다의 길이. 합이 위 총합과 같다 - 실측이
        # 있으면 실측, 없으면 예상이다.
        "scene_seconds": scene_seconds,
        # Sprint145 - 사람이 정한 차례. 적은 적이 없으면 비어 있고,
        # 그때는 위 scenes 순서가 그대로 렌더 차례다.
        "timeline": scene_order.load(path),
        "metadata": _review_metadata(path),
        # Sprint147 - 지금 올리면 무엇이 걸리는가. 화면이 짐작하지
        # 않고 이 목록을 그대로 보여 준다.
        "publish_problems": publish_gate.problems(path),
        # Sprint150 - 내 PC 자료가 몇 개나 있는가. 훑은 적이 없으면
        # root가 없고 전부 0이다 - 화면은 그 사실을 그대로 말한다.
        "library": _library_state(path),
        # Sprint148 - 큐에서 지금 어디쯤인가. 화면이 버튼 글자를
        # 지어내지 않고 이 값을 그대로 읽는다.
        "queue_status": studio_workflow.status_for(
            path,
            studio_workflow.load_store(_workflow_store()).get(project_id),
            project_id in _running_projects(),
            project_id in _uploading_projects(),
        ),
        # 썸네일이 실제로 있는가. 없으면 화면이 있는 척하지 않는다.
        "thumbnail_url": (
            f"/studio/api/projects/{project_id}/media/thumbnail"
            if os.path.exists(os.path.join(path, publish_gate.THUMBNAIL))
            else None
        ),
        "scenes": [
            {
                **scene,
                "image_url": (
                    f"/studio/api/projects/{project_id}"
                    f"/media/scene?scene={scene['scene']}"
                    if scene["has_image"] else None
                ),
                "voice_url": (
                    f"/studio/api/projects/{project_id}"
                    f"/media/voice_scene?scene={scene['scene']}"
                    if scene["has_voice"] else None
                ),
            }
            for scene in state["scenes"]
        ],
    }


class MediaPolicyRequest(BaseModel):
    mode: str
    # 장수를 알면 최대 몇 장까지 만들지 셀 수 있다. 모르면 0 이다 -
    # 지어내지 않는다.
    scene_count: int = 0


def _media_policy_view(project_path: str, scene_count: int = 0) -> dict:
    """
    화면이 한 번에 그릴 수 있게 모아 준다.

    갈래 목록도 상태도 상한도 media_policy 가 정한 것을 그대로 옮긴다 -
    화면이 제 나름대로 지으면 두 곳이 목록을 들게 되고, 어느 날 한쪽만
    늘어난다.
    """

    from app.services import media_policy

    mode = media_policy.mode_for(project_path)

    states = media_policy.provider_states(mode)

    return {
        "mode": mode,
        "label": media_policy.LABELS[mode],
        "ai_allowed": media_policy.ai_allowed(mode),
        "ai_is_the_point": media_policy.ai_is_the_point(mode),
        "modes": [
            {
                "mode": name,
                "label": media_policy.LABELS[name],
                "mine": media_policy.mine_allowed(name),
                "stock": media_policy.stock_allowed(name),
                "ai": media_policy.ai_allowed(name),
            }
            for name in media_policy.MODES
        ],
        "providers": {
            name: {
                **row,
                # 고를 수 있는가. 상태를 화면이 다시 해석하지 않게
                # 여기서 한 번만 정한다 - 쓸 수 없는 것을 고를 수
                # 있게 내놓으면 사람은 눌러 보고 시간을 버린다.
                "choosable": row["state"] == media_policy.AVAILABLE,
            }
            for name, row in states.items()
        },
        "plan": media_policy.plan_for(mode, scene_count=scene_count),
    }


@router.get("/api/review/{project_id}/media-policy")
def review_media_policy(project_id: str, scene_count: int = 0):
    """이 프로젝트가 무엇으로 만들기로 했는가."""

    return _media_policy_view(_project_path(project_id), scene_count)


@router.put("/api/review/{project_id}/media-policy")
def review_save_media_policy(project_id: str, request: MediaPolicyRequest):
    """
    사람이 고른 제작 방식을 프로젝트에 적는다.

    새 저장소를 만들지 않는다 - project.json 의 한 칸이고,
    provider_selection 이 이미 그 파일에 산다.
    """

    from app.services import media_policy

    path = _project_path(project_id)

    try:
        media_policy.choose(path, request.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _media_policy_view(path, request.scene_count)


@router.put("/api/review/{project_id}/providers")
def review_save_providers(project_id: str, request: ReviewProviderRequest):
    """
    이 프로젝트가 어느 Provider로 만들지 적는다.

    환경변수를 바꾸지 않는다 - 프로젝트에 적고, 만들 때 그 프로젝트를
    아는 자리가 읽는다.
    """

    from app.services import provider_selection

    path = _project_path(project_id)
    registry = _registry()

    for stage, name in (request.providers or {}).items():
        try:
            provider_selection.require_stage(stage)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if name in (None, "", provider_selection.CURRENT):
            continue

        # 모르는 이름을 적어 두면 만들 때가 되어서야 깨진다.
        #
        # 받아 줄 이름은 두 층에서 온다.
        #
        #   엔진이 아는 이름   provider_selection.WIRED - 지금 실제로
        #                      도는 것들(음성 google·elevenlabs,
        #                      메타데이터 manual)
        #   등록소의 이름      app.production - 아직 안 붙은 자리들
        #                      (Sprint124). 골라 두면 만들 때 정직하게
        #                      거절한다
        #
        # 둘은 겹치지 않는다. 등록소의 "google_tts"는 모델을 직접 부르는
        # 다른 자리이고, 엔진의 "google"은 지금 도는 경로다.
        if not _known_provider(stage, name, registry):
            raise _unknown_provider_error(stage, name, registry)

    try:
        provider_selection.save(path, request.providers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return review_state(project_id)


@router.post("/api/review/{project_id}/script")
def review_generate_script(project_id: str):
    """STEP1. 기존 Writer를 부른다."""

    from app.services import studio_review

    path = _project_path(project_id)
    meta = studio_service._load(os.path.join(path, "project.json")) or {}

    try:
        studio_review.generate_script(meta.get("topic") or "", path)
    except studio_review.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return review_state(project_id)


@router.put("/api/review/{project_id}/script")
def review_save_script(project_id: str, request: ReviewScriptRequest):
    """사람이 고친 대본을 확정한다. 다시 만들지 않는다."""

    from app.services import scene_order, studio_review

    path = _project_path(project_id)

    try:
        studio_review.save_script(path, request.data)
    except studio_review.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Sprint145 - 차례는 따로 적는다. 대본이 먼저 통과한 뒤에만 적는다 -
    # 거절당한 대본의 차례를 남겨 두면 다음에 어긋난 것을 읽는다.
    if request.timeline is not None:
        scene_order.save(
            path,
            order=request.timeline.get("order"),
            deleted=request.timeline.get("deleted"),
        )

    return review_state(project_id)


def _workspace_store() -> str:
    # 경로 정의는 free_workspace 한 곳에만 둔다.
    from app.services import free_workspace

    return free_workspace.default_store_path()


@router.get("/api/workspace")
def workspace_state():
    """
    Sprint152 - 정해 둔 내 자료 폴더와 그 안에 무엇이 몇 개 있는가.

    정한 적이 없으면 root가 없고 전부 0이다. 화면은 그 사실을 그대로
    말한다 - 있는 척하지 않는다.
    """

    from app.services import free_workspace

    # Sprint153 - 어떤 폴더를 만들어야 하는지도 함께 말한다. 처음
    # 쓰는 사람은 images/videos/voices/music을 모른다.
    return free_workspace.status(_workspace_store())


@router.put("/api/workspace")
def workspace_choose(request: WorkspaceRequest):
    """Sprint152 - 이 폴더를 쓰겠다. 파일은 읽기만 한다."""

    from app.services import free_workspace

    from app.services import beta_telemetry

    try:
        free_workspace.remember(_workspace_store(), request.root)
    except free_workspace.WorkspaceError as exc:
        beta_telemetry.note_failure(exc)

        raise HTTPException(status_code=400, detail=str(exc))

    # Sprint175 - 어디까지 갔는지만 적는다. 어느 폴더를 골랐는지는
    # 적지 않는다 - 그것은 사람의 것이다.
    beta_telemetry.note(beta_telemetry.WORKSPACE_SELECTED)

    return free_workspace.status(_workspace_store())


@router.get("/api/review/{project_id}/preparation")
def review_preparation(project_id: str):
    """
    Sprint152 - 이 프로젝트를 무료로 만들 수 있는가. Scene마다.

    고쳐 주지 않고 만들지도 않는다. 무엇이 있고 무엇이 없는지만
    말한다 - 렌더를 누르고 몇 분 뒤에 아는 것보다 낫다.
    """

    from app.services import beta_telemetry, free_workspace, studio_review

    path = _project_path(project_id)
    scenes = studio_review.state(path).get("scenes") or []

    found = free_workspace.preparation(path, scenes)

    # Sprint175 - 준비가 됐다는 사실만. 어느 파일이 걸렸는지는 적지
    # 않는다. 프로젝트마다 한 번이다 - 화면이 이 자리를 여러 번 본다.
    if found.get("state") == "ready":
        beta_telemetry.note(beta_telemetry.PREPARATION_READY,
                            once=project_id)

    return found


def _library_item(path: str, wanted: str):
    """
    훑어 둔 목록에서 그 경로를 찾는다. 없으면 None.

    목록에 있는 것만 내주고 받는다 - 없으면 요청 하나로 이 컴퓨터의
    아무 파일이나 읽어 갈 수 있다.
    """

    from app.services import local_library

    if not wanted:
        return None

    target = os.path.normcase(os.path.abspath(wanted))

    for item in local_library.load(path).get("items") or []:
        if os.path.normcase(os.path.abspath(item["path"])) == target:
            return item

    return None


@router.get("/api/review/{project_id}/asset")
def review_asset(project_id: str, path: str = ""):
    """
    Sprint158 - 내 자료 파일 하나를 그대로 내준다. 미리보기용이다.

    훑어 둔 목록에 있는 것만 내준다. 목록에 없는 경로는 404다 -
    있는지 없는지도 알려 주지 않는다.
    """

    project = _project_path(project_id)
    item = _library_item(project, path)

    if item is None or not os.path.exists(item["path"]):
        raise HTTPException(status_code=404, detail="그런 자료가 없습니다.")

    return FileResponse(item["path"])


@router.get("/api/review/{project_id}/scenes/{scene}/alternatives")
def review_scene_alternatives(project_id: str, scene: int):
    """
    Sprint158 - 이 scene에 쓸 수 있는 다른 파일들.

    낱말이 겹치는 것을 위에 두되, 안 겹치는 것도 모두 준다 - 안
    겹치는 것만 가진 사람이 바로 그것을 바꾸고 싶어 한다.

    만들지 않는다. 고르지도 않는다 - 지금 무엇이 걸려 있는지와
    무엇으로 바꿀 수 있는지만 말한다.
    """

    from app.providers import local_stock_provider
    from app.services import local_library, studio_review

    path = _project_path(project_id)

    found = next(
        (s for s in (studio_review.state(path).get("scenes") or [])
         if s.get("scene") == scene),
        None,
    )

    if found is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene}이 없습니다.")

    prompt = found.get("image_prompt") or ""
    chosen = local_stock_provider.match(path, prompt, scene)

    index = local_library.load(path)
    words = local_stock_provider._keywords(prompt)

    scored = {}

    for kind in (local_library.IMAGES, local_library.VIDEOS):
        for item, matched in local_library.search_scored(index, words, kind):
            scored[os.path.normcase(item["path"])] = (item, matched)

    rows = []

    for item in index.get("items") or []:
        if item["kind"] not in (local_library.IMAGES, local_library.VIDEOS):
            continue

        key = os.path.normcase(item["path"])

        if chosen and key == os.path.normcase(chosen["path"]):
            continue

        matched = scored.get(key, (None, []))[1]

        rows.append({
            "file": item["name"],
            "path": item["path"],
            "kind": item["kind"],
            "matched_keywords": matched,
            "matched_count": len(matched),
        })

    rows.sort(key=lambda row: (-row["matched_count"], row["path"]))

    return {
        "scene": scene,
        "total_keywords": len(words),
        "chosen": None if chosen is None else {
            "file": chosen["file"], "path": chosen["path"],
            "kind": chosen["kind"],
            "matched_keywords": chosen["matched_keywords"],
            "matched_count": chosen["matched_count"],
            "chosen_by": chosen["chosen_by"],
        },
        "alternatives": rows,
    }


@router.put("/api/review/{project_id}/scenes/{scene}/asset")
def review_choose_asset(project_id: str, scene: int,
                        request: SceneAssetRequest):
    """
    Sprint158 - 이 scene에는 이 파일을 쓰겠다.

    사람의 결정만 적는다. 여기서 무엇을 만들지 않는다 - 실제로 놓는
    것은 예전과 같이 이미지 생성 단계가 한다.
    """

    from app.services import asset_override, local_library

    path = _project_path(project_id)
    item = _library_item(path, request.path)

    if item is None:
        raise HTTPException(
            status_code=400,
            detail="훑어 둔 내 자료에 없는 파일입니다.",
        )

    if item["kind"] not in (local_library.IMAGES, local_library.VIDEOS):
        raise HTTPException(
            status_code=400,
            detail=f"그림이나 영상이어야 합니다: {item['name']}",
        )

    asset_override.save(path, scene, item["path"])

    return {"scene": scene, "file": item["name"], "path": item["path"],
            "kind": item["kind"]}


@router.delete("/api/review/{project_id}/scenes/{scene}/asset")
def review_clear_asset(project_id: str, scene: int):
    """Sprint158 - 정한 것을 지운다. 자동으로 고른 것으로 돌아간다."""

    from app.services import asset_override

    asset_override.clear(_project_path(project_id), scene)

    return {"scene": scene, "cleared": True}


def _scene_row(path: str, scene: int):
    """
    준비 상태에서 그 Scene 한 줄을 꺼낸다.

    판정을 여기서 다시 하지 않는다 - 화면이 보는 그 값을 그대로
    본다. 두 곳에서 따로 재면 확인 버튼이 눌리는 조건과 화면에 뜬
    상태가 갈린다.
    """

    from app.services import free_workspace, studio_review

    scenes = studio_review.state(path).get("scenes") or []
    report = free_workspace.preparation(path, scenes)

    for row in report["scenes"]:
        if row["scene"] == scene:
            return row

    return None


@router.post("/api/review/{project_id}/scenes/{scene}/confirm")
def review_confirm_scene(project_id: str, scene: int):
    """
    Sprint161 - 봤고 괜찮다.

    무엇도 바꾸지 않는다. 사람이 본 것을 적을 뿐이다 - 확인했다고
    우리가 더 나은 파일로 바꿔 주면, 사람이 확인한 것과 실제로
    쓰이는 것이 달라진다.
    """

    from app.services import free_workspace, review_confirm

    path = _project_path(project_id)
    row = _scene_row(path, scene)

    if row is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene}이 없습니다.")

    if row["state"] == free_workspace.BLOCKED:
        raise HTTPException(
            status_code=400,
            detail=(f"Scene {scene}은 아직 없는 것이 있습니다. "
                    "없는 것은 확인으로 넘길 수 없습니다."),
        )

    if row["state"] != free_workspace.REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Scene {scene}은 검토할 것이 없습니다.",
        )

    # 무엇에 대한 확인인지는 free_workspace가 정한다 - 여기서 따로
    # 고르면 적을 때와 견줄 때가 다른 것을 가리킨다.
    review_confirm.save(
        path, scene, free_workspace.review_anchor(row["image"]),
        row["reasons"],
    )

    return {"scene": scene, "confirmed": True, "reasons": row["reasons"]}


@router.delete("/api/review/{project_id}/scenes/{scene}/confirm")
def review_unconfirm_scene(project_id: str, scene: int):
    """Sprint161 - 확인을 지운다. 다시 검토 필요가 된다."""

    from app.services import review_confirm

    review_confirm.clear(_project_path(project_id), scene)

    return {"scene": scene, "confirmed": False}


@router.get("/api/review/{project_id}/completion")
def review_completion(project_id: str):
    """
    Sprint166 - 무엇으로 만들어졌는가.

    새로 적지 않는다. project.json·검사 결과·준비 상태에 이미 있는
    것을 읽어 옮긴다 - 적어 두면 그것이 또 하나의 진실이 되고 실제
    파일과 갈리는 날이 온다.
    """

    from app.services import completion_report, studio_review

    path = _project_path(project_id)
    scenes = studio_review.state(path).get("scenes") or []

    return completion_report.build(path, scenes)


@router.get("/api/review/{project_id}/output-check")
def review_output_check(project_id: str):
    """
    Sprint163 - 만든 뒤에 결과를 본다.

    읽고 말하기만 한다. 빠진 것을 우리가 만들어 주면, 사람은 무엇이
    빠졌는지 영영 모른 채 다음에도 같은 자리에서 걸린다.
    """

    from app.services import beta_telemetry, output_check, studio_review

    path = _project_path(project_id)
    scenes = studio_review.state(path).get("scenes") or []

    found = output_check.build(path, scenes)

    # Sprint175 - 검사에서 걸렸다는 사실만. 무엇이 걸렸는지(scene 번호,
    # 파일 이름)는 적지 않는다.
    if found.get("state") == output_check.FAILED:
        beta_telemetry.note(beta_telemetry.OUTPUT_CHECK_FAILED,
                            once=project_id)

    return found


@router.get("/api/review/{project_id}/final-check")
def review_final_check(project_id: str):
    """
    Sprint162 - 누르기 전에 마지막으로 본다.

    읽고 말하기만 한다. 막는 일은 예전부터 있던 렌더 검사가 하고,
    여기서는 그것을 그대로 읽어 옮긴다 - 두 곳에서 따로 판정하면
    화면이 "가능"이라고 한 것을 서버가 거절하는 날이 온다.
    """

    from app.services import final_check, studio_review

    path = _project_path(project_id)
    scenes = studio_review.state(path).get("scenes") or []

    return final_check.build(path, scenes)


@router.get("/api/review/{project_id}/requirements")
def review_requirements(project_id: str):
    """
    Sprint153 - 무엇이 필요하고 어디에 두면 되는가. Scene마다 한 줄씩.

    만들지 않는다. 고르지도 않는다 - 읽고 말하기만 한다. AI 이미지도
    TTS도 스톡 검색도 이 경로에서는 불리지 않는다.
    """

    from app.services import free_workspace, studio_review

    path = _project_path(project_id)
    scenes = studio_review.state(path).get("scenes") or []

    return free_workspace.requirements(path, scenes)


@router.post("/api/review/{project_id}/library")
def review_scan_library(project_id: str, request: LibraryScanRequest):
    """
    Sprint150 - 내 PC 폴더를 훑어 목록을 만든다.

    파일은 한 바이트도 건드리지 않는다. 읽어서 목록만 적는다 - 무료
    제작 모드가 그 목록에서 고른다.
    """

    from app.services import free_workspace, local_library

    path = _project_path(project_id)
    root = (request.root or "").strip()

    # Sprint152 - 주지 않았으면 정해 둔 폴더를 쓴다. 프로젝트마다 같은
    # 경로를 다시 적게 만들지 않는다.
    if not root:
        root = free_workspace.remembered(_workspace_store())["root"] or ""

        if not root:
            raise HTTPException(
                status_code=400,
                detail="내 자료 폴더를 먼저 고르십시오.",
            )

    if not os.path.isdir(root):
        raise HTTPException(
            status_code=400, detail=f"그런 폴더가 없습니다: {root}",
        )

    index = local_library.scan(root)
    local_library.save(path, index)

    return {
        "root": root,
        "counts": local_library.counts(index),
        "total": len(index["items"]),
    }


@router.put("/api/review/{project_id}/metadata")
def review_save_metadata(project_id: str, request: ReviewMetadataRequest):
    """
    사람이 고친 제목·설명·태그를 확정한다. 다시 만들지 않는다.

    새로 만드는 것은 없다 - 놓여 있는 publish_package.json의 그 세 칸만
    바꿔 다시 적는다. 없으면 만들지 않고 거절한다.
    """

    from app.services import publish_gate

    path = _project_path(project_id)

    try:
        publish_gate.save_edits(path, request.metadata or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return review_state(project_id)


def _chosen_image_provider_refused(project_path: str, exc: Exception):
    """
    Sprint225 - 고른 것으로 만들지 못했다. 무엇을 골랐는지 함께 말한다.

    고른 것이 없으면(current) None을 돌려준다 - 그때는 부르는 쪽이
    예전 그대로 그냥 던진다. 이 회차는 고른 사람의 화면만 고친다.

    왜 라우터인가
    -------------
    이름표(GENERATED_IMAGE_PROVIDERS)는 app.production에 있고, 서비스가
    그것을 들이면 test_production_architecture가 막는다. 이 라우터는
    이미 app.production을 들이는 자리다(script-check가 그렇게 한다).

    무엇을 고쳤는지에 대해 정직하게
    -------------------------------
    지금까지 이 자리는 ReviewError만 받았다. 고른 Provider가 내는 것은
    RuntimeError 갈래라(LocalStockUnavailable · FluxUnavailable ·
    GptImageUnavailable · ProviderNotWired) 그대로 빠져나가 500이 됐고,
    화면에는 "Internal Server Error"만 떴다 - 정작 사람이 할 수 있는
    일(파일 이름을 고치거나 자료를 더 넣는 것)이 적힌 그 문장이
    사라진 것이다.
    """

    from app.production.providers.generated_image import (
        GENERATED_IMAGE_PROVIDERS,
    )
    from app.services import provider_selection

    chosen = provider_selection.selected(project_path, "image")

    if not chosen:
        return None

    display = next(
        (row[1] for row in GENERATED_IMAGE_PROVIDERS if row[0] == chosen),
        chosen,
    )

    return (
        f"'{display}'(으)로 만들지 못했습니다. {exc} "
        f"다른 것으로 만들려면 만들 것을 먼저 바꾸십시오."
    )


@router.post("/api/review/{project_id}/images")
def review_generate_images(project_id: str):
    """STEP1 승인 -> STEP2. 확정된 대본으로 이미지를 만든다."""

    from app.services import studio_review

    path = _project_path(project_id)
    meta = studio_service._load(os.path.join(path, "project.json")) or {}

    try:
        studio_review.generate_images(path, meta.get("channel") or "wellbeing")
    except studio_review.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        # Sprint225 - 고른 것이 만들지 못한 경우. 고르지 않았으면
        # 예전 그대로 던진다.
        refused = _chosen_image_provider_refused(path, exc)

        if refused is None:
            raise

        raise HTTPException(status_code=400, detail=refused)

    return review_state(project_id)


@router.post("/api/review/{project_id}/images/{scene}")
def review_regenerate_image(project_id: str, scene: int):
    """Scene 하나만 다시 만든다. 나머지는 손대지 않는다."""

    from app.services import studio_review

    path = _project_path(project_id)
    meta = studio_service._load(os.path.join(path, "project.json")) or {}

    try:
        studio_review.regenerate_image(
            path, meta.get("channel") or "wellbeing", scene,
        )
    except studio_review.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        refused = _chosen_image_provider_refused(path, exc)

        if refused is None:
            raise

        raise HTTPException(status_code=400, detail=refused)

    return review_state(project_id)


@router.post("/api/review/{project_id}/voices")
def review_generate_voices(project_id: str):
    """STEP2 승인 -> STEP3. 확정된 대본으로 나레이션을 만든다."""

    from app.services import studio_review

    path = _project_path(project_id)

    try:
        studio_review.generate_voices(path)
    except studio_review.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return review_state(project_id)


@router.post("/api/review/{project_id}/voices/{scene}")
def review_regenerate_voice(project_id: str, scene: int):
    """Scene 하나만 다시 만든다."""

    from app.services import studio_review

    path = _project_path(project_id)

    try:
        studio_review.regenerate_voice(path, scene)
    except studio_review.ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return review_state(project_id)


@router.post("/api/review/{project_id}/render")
def review_render(project_id: str):
    """
    STEP3 승인 -> STEP4.

    새 Render를 만들지 않는다. 생성 버튼이 쓰는 그 작업을 그대로 걸면
    Resolver들이 확정된 대본·이미지·음성을 보고 01·02·03을 건너뛴다.
    """

    from app.services import scene_order, studio_review

    path = _project_path(project_id)
    meta = studio_service._load(os.path.join(path, "project.json")) or {}

    # Sprint145 - 걸기 전에 본다. 렌더 도중에 멈추면 이미 몇 분을 쓴
    # 뒤이고, 그때의 실패 문구는 사람이 읽을 수 있는 말이 아니다.
    state = studio_review.state(path)
    problems = scene_order.render_problems(path, state.get("scenes") or [])

    from app.services import beta_telemetry

    if problems:
        # 무엇이 막았는지는 적지 않는다 - 그 문장에는 scene 번호와
        # 파일 이름이 들어 있다.
        beta_telemetry.note_failure("render_blocked")

        raise HTTPException(status_code=400, detail=" · ".join(problems))

    job_id = studio_review.render(
        meta.get("topic") or "",
        project_id,
        meta.get("channel") or "wellbeing",
    )

    # 시작도 만드는 실이 적는다(Sprint176) - 여기서 또 적으면 두 번이다.

    return {"job_id": job_id}


@router.get("/api/projects/{project_id}/regeneration")
def regeneration(project_id: str):
    """엔진이 남긴 결정 로그와 scene별 재시도/되돌리기 상태."""

    return studio_regeneration.regeneration_view(_project_path(project_id))


@router.post("/api/projects/{project_id}/regenerate")
def regenerate(project_id: str, request: RegenerateRequest = None):
    """
    재생성을 시작한다. 무엇을 다시 그릴지는 엔진이 정한다 - 여기서는
    범위만 넘긴다.
    """

    path = _project_path(project_id)
    scenes = (request.scenes if request else None) or None

    return {
        "job_id": studio_jobs.start_regeneration(project_id, path, scenes),
    }


# Sprint90 - OAuth 4개 엔드포인트. Upload Runtime은 아직 연결하지 않는다.
#
# 상태 조회만 동기다(로컬 토큰 파일만 읽으므로 즉시 끝난다). 나머지
# 셋은 백그라운드 작업으로 돌린다 - 특히 로그인은 브라우저 리다이렉트를
# 기다리며 수백 초 블로킹할 수 있다.
_OAUTH_ACTIONS = ("login", "refresh", "logout")


@router.get("/api/oauth/status")
def oauth_status():
    """
    저장된 자격증명 상태. 로컬 파일만 읽고 Network를 치지 않는다 -
    화면을 열 때마다 불려도 안전해야 하고, 무엇보다 브라우저가 저절로
    열리면 안 된다.
    """

    manager = oauth_manager.build_default_oauth_manager()
    health = manager.check_health()

    return {
        "status": health.status,
        "message": health.message,
        "checked_at": health.checked_at,
        "account_id": manager.account_id,
        # 어디를 읽고 있는지 화면이 보여줄 수 있어야 한다 - 자격증명이
        # 없을 때 어디에 두면 되는지가 그것으로 드러난다.
        "token_store_path": getattr(manager.token_store, "storage_path", None),
        "client_secret_path": getattr(
            manager.oauth_service, "client_secret_path", None,
        ),
    }


@router.post("/api/oauth/{action}")
def oauth_action(action: str):
    """
    login / refresh / logout.

    login만 브라우저를 연다. 사용자가 버튼을 눌렀을 때만 이 경로가
    호출되며, 상태 조회(GET)는 절대 여기로 오지 않는다.
    """

    if action not in _OAUTH_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"알 수 없는 OAuth 동작입니다: {action!r}. "
                   f"사용 가능한 값: {list(_OAUTH_ACTIONS)}",
        )

    return {"job_id": studio_jobs.start_oauth(action)}


# ── Sprint217 - SNS 계정 (Epic 61) ───────────────────────────────────
#
# YouTube 하나만 있던 자리를 세 플랫폼으로 넓힌다. 위의 /api/oauth/*
# 는 지우지 않는다 - 이미 그 경로를 부르는 것이 있고(테스트 포함),
# YouTube의 같은 자격증명을 같은 Manager로 다룬다.

_SOCIAL_ACTIONS = ("login", "logout", "refresh")


class QueueUploadRequest(BaseModel):
    project_id: str
    platform: str


@router.get("/api/publish/queue")
def publish_queue_view():
    """
    올릴 차례로 서 있는 것들. 여기서 올리지 않는다 - 줄만 보여 준다.
    """

    from app.services import publish_queue

    return {"items": publish_queue.every(publish_queue.default_store_path())}


@router.post("/api/publish/queue")
def publish_queue_add(request: QueueUploadRequest):
    """
    줄에 세운다. 아직 올리지 않는다 - 올리는 일꾼은 다음 걸음이다.

    올릴 것이 없는데 세우지 않는다. 세워 두면 사람은 줄에 있는 것을
    보고 올라갈 것이라 믿고, 나중에 "영상이 없다"는 말을 듣는다.
    """

    from app.services import publish_queue
    from app.services.studio_service import MEDIA_KINDS

    project_path = _project_path(request.project_id)

    # 산출물 이름은 studio_service 가 정한 것을 그대로 쓴다. 여기서
    # 다시 적지 않는다.
    #
    # publishing 계층에도 같은 일을 하는 함수가 있지만 부르지 않는다 -
    # 그 계층을 쓰는 곳은 instagram_upload_step_service 한 곳뿐이라는
    # 경계가 있고(test_only_the_instagram_step_uses_the_adapter), 줄과
    # 화면은 그것을 몰라야 한다. 실제로 그 가드에 걸렸다.
    video = os.path.join(project_path, *MEDIA_KINDS["video"].split("/"))

    if not os.path.isfile(video):
        raise HTTPException(
            status_code=400,
            detail="아직 영상이 없습니다. 영상을 먼저 만들어 주십시오.")

    # Sprint238 - 이미 올린 것은 다시 세우지 않는다.
    #
    # 줄은 제 안의 SUCCESS 만 안다. 줄 밖에서 올린 것(손으로 부른
    # 업로드 스텝)은 모르고, 그대로 두면 같은 영상이 채널에 두 번
    # 올라간다. 실제로 그런 기록이 이 PC 에 있었다.
    from app.services import publish_history

    done = publish_history.already_published(project_path, request.platform)

    if done:
        # 거절이 아니다. 이미 끝난 일이라고 알려 주고 그때 주소를
        # 그대로 준다 - 사람이 찾아갈 수 있어야 한다.
        return {
            "state": publish_queue.SUCCESS,
            "project_id": request.project_id,
            "platform": request.platform,
            "url": done.get("url") or "",
            "upload_id": done.get("upload_id") or "",
            "already": True,
        }

    try:
        return publish_queue.add(
            publish_queue.default_store_path(),
            project_id=request.project_id, platform=request.platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/social/accounts")
def social_accounts():
    """
    세 플랫폼의 지금 상태.

    로컬 파일만 읽는다 - 네트워크도 브라우저도 열지 않는다. 화면을 열
    때마다 불리는 자리라서, 여기서 브라우저가 열리면 그것이 곧 결함이다
    (/api/oauth/status가 지켜 온 것과 같은 규칙).
    """

    from app.services import secret_box, social_accounts as social

    manager = social.build_default_social_auth_manager()

    return {
        "accounts": [a.as_dict() for a in manager.accounts()],
        # 토큰이 디스크에 어떻게 놓이는가. 화면이 그대로 보여 준다 -
        # "안전하게 저장했다"고 말해 놓고 평문이면 그것이 거짓이다.
        "token_at_rest": "protected" if secret_box.available() else "plaintext",
    }


@router.post("/api/social/{platform}/{action}")
def social_action(platform: str, action: str):
    """
    login / logout / refresh.

    login만 브라우저를 연다. 사람이 단추를 눌렀을 때만 이 경로가
    불린다 - 상태 조회(GET)는 절대 여기로 오지 않는다.
    """

    from app.services import social_accounts as social

    if platform not in social.PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"알 수 없는 플랫폼입니다: {platform!r}. "
                   f"사용 가능한 값: {list(social.PLATFORMS)}",
        )

    if action not in _SOCIAL_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"알 수 없는 동작입니다: {action!r}. "
                   f"사용 가능한 값: {list(_SOCIAL_ACTIONS)}",
        )

    return {"job_id": studio_jobs.start_social(platform, action)}


@router.get("/api/dataset")
def dataset():
    """Dashboard의 Dataset 위젯. Sprint79 축적 파일을 읽는다."""

    from app.pipeline.pipeline import DATASET_ROOT

    rows = asset_dataset.load(
        os.path.join(DATASET_ROOT, asset_dataset.DATASET_FILENAME),
    )
    summary = asset_dataset.summarize(rows)
    summary["readiness"] = asset_dataset.readiness(rows)

    return summary


# ══════════════════════════════════════════════════════════════════
# Sprint222 - 대본보다 먼저 온 자료 (Epic 64).
#
# 왜 studio.py 안인가
# -------------------
# 처음에는 app/routers/staging.py 로 따로 두었다. 그런데
# test_production_architecture 가 "제작 Provider 등록부를 쓰는 라우터는
# studio.py 하나뿐"이라는 규칙을 지키고 있고, apply 는 그 등록부를
# 쓴다(기존 매칭을 그대로 쓰려면 반드시 그래야 한다).
#
# 가드를 고치는 대신 이쪽을 옮겼다. 등록부를 두 라우터가 쓰기 시작하면
# 어느 날 두 화면이 서로 다른 Provider 로 만들게 된다 - 그 규칙이 옳다.
#
#     POST    /studio/api/projects/{id}/staging          받는다 (대본 불필요)
#     GET     /studio/api/projects/{id}/staging          무엇이 담겼나
#     DELETE  /studio/api/projects/{id}/staging/{asset}  하나 뺀다
#     POST    /studio/api/projects/{id}/staging/apply    scene 에 연결한다
#
# 매칭을 새로 만들지 않았다 - apply 는 위의 production_images 가 하던
# 일에서 mkdtemp 와 rmtree 두 줄만 뺀 것이다.
# ══════════════════════════════════════════════════════════════════

from app.services import staging as staging_service


def _staging_scenes(path: str) -> list:
    """
    대본에서 나온 scene 들. 없으면 400.

    Resolver 를 그대로 쓴다 - 새 읽기 경로를 만들지 않는다(Sprint106).
    """

    from app.steps.step01_script_resolve import ScriptResolveError, load_prepared

    try:
        return load_prepared(path)["scenes"]
    except ScriptResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/projects/{project_id}/staging")
async def staging_add(
    project_id: str,
    kind: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """
    자료를 받아 둔다. **대본이 없어도 받는다.**

    여기서 아무것도 놓지 않는다 - 어느 scene 으로 갈지는 대본이 생긴
    뒤 apply 가 기존 provider 에게 묻는다.
    """

    path = _project_path(project_id)

    try:
        added = staging_service.add(
            path, kind, [(upload.filename, upload.file) for upload in files],
        )
    except staging_service.StagingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    found = staging_service.listing(path)

    return {
        "added": len(added),
        "assets": added,
        "counts": found["counts"],
        "total": found["total"],
    }


@router.get("/api/projects/{project_id}/staging")
def staging_view(project_id: str):
    """무엇이 담겼는가. 디스크에 실제로 있는 것만 센다."""

    return staging_service.listing(_project_path(project_id))


@router.delete("/api/projects/{project_id}/staging/{asset_id}")
def staging_remove(project_id: str, asset_id: str):
    path = _project_path(project_id)

    if not staging_service.remove(path, asset_id):
        raise HTTPException(status_code=404, detail="그런 자료가 없습니다.")

    found = staging_service.listing(path)

    return {"removed": asset_id, "counts": found["counts"],
            "total": found["total"]}


@router.post("/api/projects/{project_id}/staging/apply")
def staging_apply(project_id: str, kind: str = Form(None)):
    """
    담아 둔 자료를 scene 에 연결한다.

    kind 를 주지 않으면 담긴 종류를 전부 연결한다. 비어 있는 종류는
    건너뛴다 - 없는 것을 놓으라고 provider 를 부르면 그쪽이 던진다.

    원본은 지우지 않는다. provider 가 복사만 하므로(image_import.
    _place: "원본은 손대지 않는다") 사람이 다시 연결할 수 있다.
    """

    path = _project_path(project_id)

    kinds = [kind] if kind else list(staging_service.KINDS)

    for one in kinds:
        if one not in staging_service.KINDS:
            raise HTTPException(
                status_code=400,
                detail=f"받을 수 없는 종류입니다: {one!r}")

    ready = {one: staging_service.paths_for(path, one) for one in kinds}

    if not any(ready.values()):
        raise HTTPException(status_code=400,
                            detail="연결할 자료가 없습니다.")

    scenes = _staging_scenes(path)

    # studio 라우터의 등록부를 그대로 쓴다. 두 벌을 만들지 않는다.
    from app.production.stage_request import StageRequest

    applied = {}

    for one, given in ready.items():
        if not given:
            continue

        provider = _registry().get(one, staging_service.provider_name(one))

        try:
            result = provider.accept_manual(
                given, StageRequest(project_path=path, scenes=scenes),
            )
        except ValueError as exc:
            # ImageImportError · VoiceImportError 가 전부 ValueError 다.
            raise HTTPException(status_code=400, detail=str(exc))

        applied[one] = {
            "count": len(given),
            "scene_count": result.get("scene_count"),
            "warnings": result.get("warnings", []),
        }

    return {"applied": applied, "scene_count": len(scenes)}
