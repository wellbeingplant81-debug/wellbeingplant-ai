from pydantic import BaseModel


class VideoRequest(BaseModel):

    topic: str

    channel: str = "wellbeing"