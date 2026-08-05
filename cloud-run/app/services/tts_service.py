import os

from app.providers.tts_provider import generate_voice
from app.services import audio_policy


def create_tts(script: str, project_path: str):

    output_file = os.path.join(
        project_path,
        "audio",
        audio_policy.VOICE_FILENAME
    )

    return generate_voice(
        script,
        output_file
    )