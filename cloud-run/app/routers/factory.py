from fastapi import APIRouter
from pydantic import BaseModel

from app.services.factory_service import generate_short_video

router = APIRouter()


class FactoryRequest(BaseModel):
    topic: str


@router.post("/generate-short-video")
def create_video(request: FactoryRequest):

    return generate_short_video(request.topic)