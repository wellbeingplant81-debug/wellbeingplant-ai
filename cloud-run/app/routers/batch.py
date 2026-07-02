from fastapi import APIRouter
from pydantic import BaseModel

from app.services.factory_service import generate_short_video

router = APIRouter()


class BatchRequest(BaseModel):
    topics: list[str]


@router.post("/generate-batch")
def generate_batch(request: BatchRequest):

    results = []

    for topic in request.topics:

        result = generate_short_video(topic)

        results.append(result)

    return {
        "success": True,
        "count": len(results),
        "results": results
    }