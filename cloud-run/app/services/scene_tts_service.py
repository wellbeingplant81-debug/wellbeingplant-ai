import os

from app.providers.tts_provider import generate_voice


def create_scene_tts(
    scenes,
    project_path,
    provider=None,
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

    # Sprint95 - ProductionProfile tts_provider Activation: provider가
    # 주어지면 그대로 generate_voice()에 전달한다. 주어지지 않으면
    # (기본값 None) 지금까지처럼 인자를 생략해 기존 환경변수 기반
    # 라우팅과 완전히 동일하게 동작한다.
    generate_voice_kwargs = {}
    if provider is not None:
        generate_voice_kwargs["provider"] = provider

    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        output_file = os.path.join(
            audio_dir,
            f"scene{index}.mp3",
        )

        generate_voice(
            scene["narration"],
            output_file,
            **generate_voice_kwargs,
        )

        outputs.append(
            output_file
        )

    return outputs