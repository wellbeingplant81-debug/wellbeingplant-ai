from pydantic import BaseModel


class Subtitle(BaseModel):
    text: str
    duration: float


class Scene(BaseModel):
    scene: int
    duration: float
    narration: str
    image_prompt: str
    subtitles: list[Subtitle]


class VideoScript(BaseModel):
    title: str
    hook: str
    script: str
    duration: float
    scenes: list[Scene]