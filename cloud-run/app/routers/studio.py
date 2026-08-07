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

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app import config
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
    project_id: str = None


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
            "engine": ENGINE_FACTS[stage],
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

    registry = _registry()
    plan = ProductionPlan(mode=production_modes.ASSISTED)

    try:
        for stage, mode in (request.selections or {}).items():
            stages.require_stage(stage)
            source_modes.require_source_mode(mode)

            provider = None
            if source_modes.calls_api(mode):
                chosen = registry.available(stage, mode)
                provider = chosen[0].name if chosen else None

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

    try:
        return create_from_script(
            script,
            request.topic or script["title"],
            request.channel,
            request.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/projects/{project_id}/upload")
def upload(project_id: str):
    """
    Sprint92 - 승인된 프로젝트를 YouTube에 올린다.

    승인 여부는 studio_upload가 본다 - 여기서 다시 판정하지 않는다.
    승인되지 않았으면 작업은 정상으로 끝나고 outcome이 skipped로 온다.
    """

    path = _project_path(project_id)

    job_id = studio_jobs.start_upload(project_id, path)

    return {"job_id": job_id}


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


@router.post("/api/jobs")
def create_job(request: GenerateRequest):
    if not request.topic or not request.topic.strip():
        raise HTTPException(status_code=400, detail="주제를 입력하십시오.")

    # Sprint107 - project_id가 오면 미리 만들어 둔 프로젝트로 만든다.
    # 없으면 예전과 똑같이 새 프로젝트를 만든다. 버튼도 엔드포인트도
    # 하나 그대로다.
    return {"job_id": studio_jobs.start(request.topic.strip(),
                                        request.channel,
                                        request.project_id)}


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
