from fastapi import APIRouter
from pydantic import BaseModel

from app.services.script_service import generate_script

router = APIRouter()


class ScriptRequest(BaseModel):
    topic: str


@router.post("/generate-script")
def create_script(request: ScriptRequest):
    return generate_script(request.topic)