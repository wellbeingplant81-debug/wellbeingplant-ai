import os

from app.providers.tts_provider import generate_voice


def create_tts(script: str, project_path: str):

    output_file = os.path.join(
        project_path,
        "audio",
        "voice.mp3"
    )

    return generate_voice(
        script,
        output_file
    )