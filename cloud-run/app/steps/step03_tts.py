from app.services.tts_service import create_tts
from app.services.scene_tts_service import create_scene_tts
from app.services.audio_service import mix_audio


def run(
    scenes,
    project_path,
):

    script = " ".join(
        scene["narration"]
        for scene in scenes
    )

    create_tts(
        script,
        project_path,
    )

    create_scene_tts(
        scenes,
        project_path,
    )

    mix_audio(
        project_path,
    )