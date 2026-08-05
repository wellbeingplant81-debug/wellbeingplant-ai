import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.dependencies import project_path_or_404
from app.services.image_service import generate_image

router = APIRouter()

DEFAULT_FILENAME = "scene1.png"
ALLOWED_EXTENSION = ".png"


class ImageRequest(BaseModel):
    prompt: str

    # Sprint65 - generate_image()는 저장 경로(output_file)가 필수다.
    # 이전에는 프롬프트만 넘겨서 호출 즉시 TypeError가 났다.
    project_id: str

    filename: str = DEFAULT_FILENAME
    channel: str = "wellbeing"


def _image_output_path(project_path: str, filename: str) -> str:
    """
    프로젝트의 images/ 안으로만 쓰도록 파일명을 검증한다. project_id와
    같은 이유로, 파일명에 경로가 섞여 들어오면 프로젝트 밖을 덮어쓸 수
    있다.
    """

    name = (filename or "").strip()

    if not name or os.path.basename(name) != name or "/" in name or "\\" in name:
        raise HTTPException(
            status_code=400,
            detail=f"filename에 경로를 쓸 수 없습니다: {filename!r}",
        )

    if not name.lower().endswith(ALLOWED_EXTENSION):
        raise HTTPException(
            status_code=400,
            detail=f"filename은 {ALLOWED_EXTENSION}이어야 합니다: {filename!r}",
        )

    return os.path.join(project_path, "images", name)


@router.post("/generate-image")
def create_image(request: ImageRequest):

    project_path = project_path_or_404(request.project_id)
    output_file = _image_output_path(project_path, request.filename)

    return {
        "success": True,
        "image": generate_image(
            request.prompt,
            output_file,
            request.channel,
        ),
    }
