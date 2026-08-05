import os

from app.providers.tts_provider import generate_voice
from app.services import audio_policy


def create_scene_tts(
    scenes,
    project_path,
):

    audio_dir = os.path.join(
        project_path,
        "audio",
        "scenes",
    )

    os.makedirs(
        audio_dir,
        exist_ok=True,
    )

    outputs = []

    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        output_file = os.path.join(
            audio_dir,
            audio_policy.scene_audio_filename(index),
        )

        generate_voice(
            scene["narration"],
            output_file,
        )

        outputs.append(
            output_file
        )

    return outputs