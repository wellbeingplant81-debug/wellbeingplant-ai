import os

from app.services.scene_tts_service import create_scene_tts
from app.services.audio_service import concat_scene_audio, mix_audio


def run(
    scenes,
    project_path,
):

    scene_audio_paths = create_scene_tts(
        scenes,
        project_path,
    )

    voice_path = os.path.join(
        project_path,
        "audio",
        "voice.mp3",
    )

    concat_scene_audio(
        scene_audio_paths,
        voice_path,
    )

    mix_audio(
        project_path,
    )