from pydantic import BaseModel
from typing import List


class Scene(BaseModel):
    scene: int
    narration: str
    image_prompt: str


class ShortContent(BaseModel):
    title: str
    hook: str
    script: str
    scenes: List[Scene]