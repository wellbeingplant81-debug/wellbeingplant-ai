from fastapi import APIRouter

from app.services.final_video_service import merge_video_audio

router = APIRouter()


@router.post("/merge-video")
def merge():

    return {
        "success": True,
        "video": merge_video_audio()
    }