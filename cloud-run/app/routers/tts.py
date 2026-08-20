from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.dependencies import project_path_or_404
from app.services import voice_policy
from app.services.tts_service import create_tts

router = APIRouter()


class TTSRequest(BaseModel):
    script: str

    # Sprint65 - create_tts()는 나레이션을 프로젝트의 audio/ 아래에
    # 쓴다. 대상 프로젝트가 없으면 어디에 써야 할지 알 수 없다.
    project_id: str


@router.post("/generate-tts")
def generate(request: TTSRequest):

    project_path = project_path_or_404(request.project_id)

    # Sprint244 - 고르지 않은 유료 음성은 부르지 않는다. 그 사실이
    # 사람에게 닿아야 한다 - 500 으로 뭉개면 무엇을 고르면 되는지
    # 알 수 없다.
    # 무료 자료가 없어서 못 만든 것도 여기로 온다. 그때 유료로
    # 넘어가지 않는다 - 무엇이 없는지 말하고 멈춘다. 500 스택보다
    # 사람이 고칠 수 있는 말이 낫다.
    from app.providers.local_voice_provider import LocalVoiceUnavailable

    try:
        made = create_tts(request.script, project_path)
    except (voice_policy.PaidVoiceNotAllowed, LocalVoiceUnavailable) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "success": True,
        "file": made,
    }
