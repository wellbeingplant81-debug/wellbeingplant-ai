from fastapi import APIRouter
from pydantic import BaseModel

from app.services.image_service import generate_image

router = APIRouter()


class ImageRequest(BaseModel):
    prompt: str


@router.post("/generate-image")
def create_image(request: ImageRequest):
    return generate_image(request.prompt)