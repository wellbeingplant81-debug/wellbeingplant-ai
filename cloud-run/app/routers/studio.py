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

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.services import (
    project_service, studio_jobs, studio_regeneration, studio_replay,
    studio_service,
)
from app.tools import asset_dataset


router = APIRouter(prefix="/studio", tags=["studio"])


_STATIC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static",
)

_PAGE = os.path.join(_STATIC, "studio.html")
_REPLAY_PAGE = os.path.join(_STATIC, "replay.html")


class GenerateRequest(BaseModel):
    topic: str
    channel: str = "wellbeing"


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
    """Studio 화면."""

    try:
        with open(_PAGE, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="studio.html이 없습니다.")


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


@router.post("/api/jobs")
def create_job(request: GenerateRequest):
    if not request.topic or not request.topic.strip():
        raise HTTPException(status_code=400, detail="주제를 입력하십시오.")

    return {"job_id": studio_jobs.start(request.topic.strip(),
                                        request.channel)}


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

    return result


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
