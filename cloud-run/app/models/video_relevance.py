from pydantic import BaseModel


class VideoRelevanceScore(BaseModel):
    score: float
    reasoning: str
