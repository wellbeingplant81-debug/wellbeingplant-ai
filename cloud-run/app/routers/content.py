from fastapi import APIRouter
from pydantic import BaseModel

from app.services.content_service import generate_short

router = APIRouter()


class ContentRequest(BaseModel):
    topic: str


@router.post("/generate-short")
def generate(request: ContentRequest):
    return generate_short(request.topic)