from fastapi import APIRouter

from app.services.video_builder import build_video

router = APIRouter()


@router.post("/build-video")
def create_video():

    return build_video()