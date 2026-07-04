from pydantic import BaseModel


class Scene(BaseModel):
    scene: int
    duration: float
    narration: str
    image_prompt: str


class VideoScript(BaseModel):
    title: str
    hook: str
    script: str
    duration: float
    scenes: list[Scene]