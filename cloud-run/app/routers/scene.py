from fastapi import APIRouter
from pydantic import BaseModel

from app.services.scene_service import generate_scenes

router = APIRouter()


class SceneRequest(BaseModel):
    script: str


@router.post("/generate-scenes")
def create_scene(request: SceneRequest):
    return generate_scenes(request.script)