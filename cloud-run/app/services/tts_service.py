import os

from app.providers.tts_provider import generate_voice
from app.services import audio_policy, provider_selection


def create_tts(script: str, project_path: str):
    """
    Sprint244 - 이 문도 그 프로젝트의 결정을 읽는다.

    여기는 화면의 제작 흐름을 거치지 않는 옆문이다(POST /generate-tts).
    project_path 를 이미 받고 있으면서도 그 프로젝트가 어느 목소리를
    쓰기로 했는지는 보지 않고 있었다 - 그래서 scene 쪽에서 고른 것이
    여기서는 없는 셈이 됐다.

    Sprint243 에서 그림이 같은 일을 겪었다. 파이프라인만 막았더니
    썸네일이라는 옆문으로 유료 모델이 불렸다.
    """

    output_file = os.path.join(
        project_path,
        "audio",
        audio_policy.VOICE_FILENAME
    )

    return generate_voice(
        script,
        output_file,
        provider=provider_selection.selected(project_path, "voice"),
    )