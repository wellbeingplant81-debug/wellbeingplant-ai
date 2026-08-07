import os

from app.providers import tts_provider
from app.services import audio_policy, provider_selection


def create_scene_tts(
    scenes,
    project_path,
    provider=None,
):
    """
    Sprint126 - 어느 Provider로 만들지는 프로젝트가 정한다.

    project_path를 이미 받고 있으므로 그 프로젝트의 결정을 읽는다.
    환경변수를 바꿔 쓰지 않는 이유는 studio_jobs가 파이프라인을
    스레드로 돌리기 때문이다 - 전역을 건드리면 두 작업이 겹칠 때
    서로의 설정을 덮어쓴다.

    고르지 않았으면 None이 되고, 그러면 tts_provider가 예전처럼
    TTS_PROVIDER를 읽는다. 기존 동작이 그대로 남는다.
    """

    if provider is None:
        provider = provider_selection.selected(project_path, "voice")

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

        tts_provider.generate_voice(
            scene["narration"],
            output_file,
            provider=provider,
        )

        outputs.append(
            output_file
        )

    return outputs