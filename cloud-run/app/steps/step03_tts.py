import json
import os

from app.services.scene_tts_service import create_scene_tts
from app.services.audio_service import concat_scene_audio, mix_audio
from app.services.duration_optimizer import optimize_scene_audio


# Sprint61 - Silence-Aware Subtitle Timing. subtitle_service.py가 나중에
# 읽는 파일명 - 두 모듈이 이 상수 이름으로 암묵적 계약을 공유한다.
DURATION_OPTIMIZATION_METADATA_FILENAME = "duration_optimization.json"


def _save_duration_optimization_metadata(project_path, result):
    """
    optimize_scene_audio()가 마지막 scene 오디오 뒤에 무음을 얼마나
    붙였는지(action/pause_seconds)를 audio/duration_optimization.json에
    기록한다. subtitle_service.py가 이 값을 읽어 무음 구간까지 자막이
    늘어나는 걸 막는다(Problem 4). 이 저장은 선택적 부가 기능일 뿐이므로
    - 반환값이 예상 형태(dict)가 아니거나, 디스크 오류 등 어떤 이유로든
    실패해도 - 파이프라인(concat/mix)을 절대 막지 않는다.
    """

    if not isinstance(result, dict):
        return

    try:
        path = os.path.join(
            project_path, "audio", DURATION_OPTIMIZATION_METADATA_FILENAME,
        )

        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f)

    except Exception as exc:
        print(f"[Step03Tts] duration_optimization.json 저장 실패(무시): {exc}")


def run(
    scenes,
    project_path,
    target_duration=None,
    tolerance=None,
    tts_provider=None,
):

    # Sprint95 - ProductionProfile tts_provider Activation: 값이 있으면
    # create_scene_tts()에 provider=로 전달한다. 없으면(기본값 None)
    # 지금까지처럼 인자를 생략해 기존 환경변수 기반 라우팅과 완전히
    # 동일하게 동작한다.
    create_scene_tts_kwargs = {}
    if tts_provider is not None:
        create_scene_tts_kwargs["provider"] = tts_provider

    scene_audio_paths = create_scene_tts(
        scenes,
        project_path,
        **create_scene_tts_kwargs,
    )

    # Sprint53 - Duration Optimizer: 합성이 끝난 실제 scene mp3의
    # ffprobe 실측 길이가 43~47초를 벗어나면 마지막 scene 오디오만
    # 후처리한다. concat 전에 실행해야 voice.mp3에 보정된 결과가
    # 반영된다.
    #
    # Sprint94 - ProductionProfile Duration Target Activation:
    # target_duration/tolerance가 주어지면 그대로 optimize_scene_audio()
    # 에 전달해 목표를 override한다. 주어지지 않으면(기본값 None)
    # 지금까지처럼 인자를 생략해 기존 45/2 기본값과 완전히 동일하게
    # 동작한다.
    optimizer_kwargs = {}
    if target_duration is not None:
        optimizer_kwargs["target_duration"] = target_duration
    if tolerance is not None:
        optimizer_kwargs["tolerance"] = tolerance

    optimization_result = optimize_scene_audio(scene_audio_paths, **optimizer_kwargs)
    _save_duration_optimization_metadata(project_path, optimization_result)

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