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

        # Sprint100-2 - factory.py와 동일하게 wellbeing 채널(batch는
        # 항상 wellbeing)에 upload profile을 기본으로 쓴다.
        result = generate_short_video(
            topic=topic, channel="wellbeing", production_profile_name="upload",
        )

        results.append(result)

    return {
        "success": True,
        "count": len(results),
        "results": results
    }