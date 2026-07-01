from fastapi import APIRouter
from pydantic import BaseModel

from app.services.video_service import (
    test_connection,
    generate_video,
)

router = APIRouter()


class VideoRequest(BaseModel):
    prompt: str


@router.get("/test-ai")
def test_ai():
    return test_connection()


@router.post("/generate-video")
def generate(request: VideoRequest):
    return generate_video(request.prompt)