import os

from app.services.scene_tts_service import create_scene_tts
from app.services.audio_service import concat_scene_audio, mix_audio
from app.services.duration_optimizer import optimize_scene_audio


def run(
    scenes,
    project_path,
):

    scene_audio_paths = create_scene_tts(
        scenes,
        project_path,
    )

    # Sprint53 - Duration Optimizer: 합성이 끝난 실제 scene mp3의
    # ffprobe 실측 길이가 43~47초를 벗어나면 마지막 scene 오디오만
    # 후처리한다. concat 전에 실행해야 voice.mp3에 보정된 결과가
    # 반영된다.
    optimize_scene_audio(scene_audio_paths)

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