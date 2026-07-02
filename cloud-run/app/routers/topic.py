from fastapi import APIRouter
from pydantic import BaseModel

from app.services.topic_service import generate_topics

router = APIRouter()


class TopicRequest(BaseModel):
    category: str
    count: int


@router.post("/generate-topics")
def generate(request: TopicRequest):

    return generate_topics(
        request.category,
        request.count,
    )