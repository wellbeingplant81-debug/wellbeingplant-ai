from fastapi import APIRouter

from app.models.request import VideoRequest
from app.services.factory_service import generate_short_video


router = APIRouter()


# Sprint100-2 - "연습도 실전처럼": wellbeing 채널의 실제 업로드용 영상
# 생성은 명시적으로 다른 profile을 지정하지 않는 한 항상 upload
# profile(ElevenLabs/실제 BGM/실제 Asset Strategy/실제 Duration Target)을
# 쓴다. 다른 채널은 손대지 않는다(기존 동작 유지).
@router.post("/generate-short-video")
def create_video(
    request: VideoRequest,
):

    return generate_short_video(
        topic=request.topic,
        channel=request.channel,
        production_profile_name="upload" if request.channel == "wellbeing" else None,
    )