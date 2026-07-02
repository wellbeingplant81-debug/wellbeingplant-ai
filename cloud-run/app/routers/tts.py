from fastapi import APIRouter
from pydantic import BaseModel

from app.services.tts_service import create_tts

router = APIRouter()


class TTSRequest(BaseModel):
    script: str


@router.post("/generate-tts")
def generate(request: TTSRequest):

    return {
        "success": True,
        "file": create_tts(request.script)
    }