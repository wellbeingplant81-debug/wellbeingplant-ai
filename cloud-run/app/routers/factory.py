from fastapi import APIRouter

from app.models.request import VideoRequest
from app.services.factory_service import generate_short_video


router = APIRouter()


@router.post("/generate-short-video")
def create_video(
    request: VideoRequest,
):

    return generate_short_video(
        topic=request.topic,
        channel=request.channel,
    )