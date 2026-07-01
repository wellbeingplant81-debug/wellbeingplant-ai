from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class VideoRequest(BaseModel):
    prompt: str


@router.post("/generate-video")
def generate_video(request: VideoRequest):
    return {
        "status": "accepted",
        "message": "Video generation request received.",
        "prompt": request.prompt
    }