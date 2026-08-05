from fastapi import APIRouter
from pydantic import BaseModel

from app.routers.dependencies import project_path_or_404
from app.services.final_video_service import merge_video_audio

router = APIRouter()


class MergeVideoRequest(BaseModel):

    # Sprint65 - merge_video_audio()는 어느 프로젝트를 합칠지 알아야
    # 한다. 이전에는 이 값을 받지도 넘기지도 않아서 엔드포인트를 부르는
    # 즉시 TypeError가 났다.
    project_id: str


@router.post("/merge-video")
def merge(request: MergeVideoRequest):

    project_path = project_path_or_404(request.project_id)

    return {
        "success": True,
        "video": merge_video_audio(project_path),
    }
