from fastapi import APIRouter
from pydantic import BaseModel

from app.routers.dependencies import project_path_or_404
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

    return {
        "success": True,
        "file": create_tts(request.script, project_path),
    }
