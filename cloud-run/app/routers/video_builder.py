from fastapi import APIRouter
from pydantic import BaseModel

from app.routers.dependencies import project_path_or_404
from app.services.video_builder import build_video

router = APIRouter()


class BuildVideoRequest(BaseModel):

    # Sprint65 - build_video()도 대상 프로젝트를 받아야 한다.
    project_id: str


@router.post("/build-video")
def create_video(request: BuildVideoRequest):

    project_path = project_path_or_404(request.project_id)

    return {
        "success": True,
        "video": build_video(project_path),
    }
