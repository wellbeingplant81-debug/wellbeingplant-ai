"""
Sprint113 - 음성을 어디서 가져올지 정한다 (Epic 54, Phase 12).

Sprint106(대본)·Sprint111(이미지)과 같은 자리, 같은 원칙이다. step03
앞에 서서 고르기만 하고, AUTO면 손대지 않은 step03을 그대로 부른다.
step03_tts.py는 한 줄도 바뀌지 않는다 - 그 파일은 "나레이션을 만든다"는
일만 하고, 사용자가 이미 넣어 둔 음성을 쓸지 말지는 그 파일이 판단할
문제가 아니다.

이미지와 다른 점 하나
---------------------
step02는 이미지를 놓는 것으로 끝나지만 step03은 넷을 한다.

    create_scene_tts      나레이션을 만든다
    optimize_scene_audio  마지막 scene 뒤에 무음을 붙여 45초에 맞춘다
    concat_scene_audio    scene들을 이어 voice.wav
    mix_audio             BGM을 섞어 final_audio.wav

final_video_service는 final_audio.wav로 최종 MP4를 만든다. 그래서
step03을 통째로 건너뛰면 사용자 음성을 놓고도 소리 없는 영상이 나온다 -
"사용자 음성 사용"이 성립하지 않는다.

그래서 앞의 둘만 건너뛴다. 만들지 않고(사용자가 이미 줬다), 늘리지
않는다(optimizer는 무음을 붙인다 - 자동 늘리기 금지). 뒤의 둘은 엔진의
조립이고, AUTO가 부르는 그 함수를 그대로 부른다. 여기서 새로 만드는
것은 없다.

판정 세 가지
------------
    scene 음성 전부 있음   그대로 쓴다
    voice.wav만 있음       경고하고 AUTO로 물러선다
    일부만 있음            거절한다

voice.wav만 있을 때 물러서는 이유는 subtitle_service가 scene 오디오
개수와 scene 개수가 다르면 예외를 던지기 때문이다(subtitle_service:521).
자막 시각이 scene별 길이에서 나온다. 하나로 뭉친 것을 잘라 나눌 수는
없다 - 경계를 우리가 알 수 없고, 자르는 것은 자동 분할이다.

일부만 있을 때 물러서지 않는 이유는 다르다. 그것은 사용자가 아직 다
넣지 않았다는 뜻이고, 조용히 TTS로 덮으면 이미 넣은 것이 사라진다.
멈추고 무엇이 없는지 말하는 편이 낫다.
"""

import json
import os

from app.services import audio_policy

AUTO = "auto"
IMPORT = "import"
MANUAL = "manual"

SOURCES = (AUTO, IMPORT, MANUAL)

# 사용자가 직접 넣은 음성을 쓰는 두 가지. 화면에서 폴더를 고르든
# 파일을 끌어다 놓든 결과는 같은 자리의 같은 파일이라, 갈라야 할
# 이유가 없다.
PREPARED_SOURCES = (IMPORT, MANUAL)

# 단계마다 출처가 다를 수 있으므로(Sprint109) 음성은 음성의 칸을 쓴다.
SOURCE_FIELD = "voice_source"

PROJECT_FILENAME = "project.json"

AUDIO_DIRNAME = "audio"
SCENES_DIRNAME = "scenes"


class VoiceResolveError(ValueError):
    """준비된 음성을 쓸 수 없다.

    무엇이 왜 안 되는지 적는다 - 사람이 고쳐서 다시 넣을 수 있어야
    한다."""


def _audio_dir(project_path):
    return os.path.join(project_path, AUDIO_DIRNAME)


def _scenes_dir(project_path):
    return os.path.join(_audio_dir(project_path), SCENES_DIRNAME)


def _scene_path(project_path, number):
    return os.path.join(
        _scenes_dir(project_path), audio_policy.scene_audio_filename(number),
    )


def _voice_path(project_path):
    return os.path.join(_audio_dir(project_path), audio_policy.VOICE_FILENAME)


def _placed_numbers(project_path):
    """놓여 있는 scene 번호들. 파일이 실제로 있는 것만 센다."""

    scenes_dir = _scenes_dir(project_path)

    if not os.path.isdir(scenes_dir):
        return []

    stem, suffix = audio_policy.scene_audio_filename("\0").split("\0")
    found = []

    for name in os.listdir(scenes_dir):
        if not (name.startswith(stem) and name.endswith(suffix)):
            continue

        digits = name[len(stem):len(name) - len(suffix)]
        if digits.isdigit():
            found.append(int(digits))

    return sorted(found)


def source_from_metadata(project_path):
    """사람이 고른 것이 적혀 있으면 그것. 없으면 None."""

    path = os.path.join(project_path, PROJECT_FILENAME)

    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as f:
            recorded = json.load(f).get(SOURCE_FIELD)
    except (OSError, ValueError):
        # 읽을 수 없는 project.json 때문에 제작이 멈추지는 않는다.
        return None

    return recorded if recorded in SOURCES else None


def detect_source(project_path):
    """
    적힌 것 > 디스크 > AUTO.

    디스크를 보는 이유는 create_project()가 audio/를 비운 채로 만들기
    때문이다. 비어 있으면 아직 아무도 넣지 않았다는 뜻이다.

    voice.wav 하나만 있어도 "넣었다"로 본다 - 쓸 수 있는지는 여기서
    정하지 않고 validate()가 정한다. 판정과 검증을 섞으면 왜 AUTO로
    갔는지 사용자에게 말해 줄 수 없다.
    """

    recorded = source_from_metadata(project_path)

    if recorded:
        return recorded

    if _placed_numbers(project_path) or os.path.exists(
        _voice_path(project_path)
    ):
        return IMPORT

    return AUTO


def validate(scenes, project_path):
    """
    준비된 음성으로 갈 수 있는지 본다. 고쳐 주지 않는다.

    돌려주는 것은 셋 중 하나다.

        ("ready", 경로들)   scene 음성이 전부 있다
        ("fallback", 사유)  voice.wav만 있다 - AUTO로 물러선다
        거절                일부만 있다
    """

    expected = [
        scene.get("scene", index + 1) for index, scene in enumerate(scenes)
    ]
    paths = [_scene_path(project_path, number) for number in expected]
    missing = [
        number for number, path in zip(expected, paths)
        if not os.path.exists(path)
    ]

    if not missing:
        return "ready", paths

    if len(missing) == len(expected) and os.path.exists(
        _voice_path(project_path)
    ):
        return "fallback", (
            f"{audio_policy.VOICE_FILENAME} 하나만 있습니다 - Scene "
            f"{len(expected)}개의 자막 시각을 내려면 Scene마다 하나씩 "
            "있어야 합니다. 이번에는 음성을 새로 만듭니다."
        )

    raise VoiceResolveError(
        f"Scene {len(expected)}개인데 음성은 "
        f"{len(expected) - len(missing)}개입니다 - "
        f"Scene {', '.join(str(n) for n in missing)}의 음성이 없습니다. "
        "음성을 채운 뒤 다시 실행하거나, 음성 생성을 자동으로 "
        "바꾸십시오."
    )


def assemble(paths, project_path):
    """
    엔진의 조립을 그대로 부른다. 새로 만드는 것은 없다.

    optimize_scene_audio는 부르지 않는다 - 그것은 마지막 scene 뒤에
    무음을 붙여 길이를 맞추는 일이고, 사용자가 준 음성에 그것을 하는
    것이 자동 늘리기다.
    """

    # 늦게 부른다 - AUTO 경로에는 필요 없고, audio_service는 읽는
    # 것만으로 ffmpeg 계층을 끌고 온다.
    from app.services import audio_service

    audio_service.concat_scene_audio(paths, _voice_path(project_path))
    audio_service.mix_audio(project_path)


def run(scenes, project_path, source=None):
    """
    음성 단계 입구.

    준비된 음성이 있으면 그것을 쓰고, 없으면 step03을 그대로 부른다.
    AUTO 경로는 예전과 완전히 같아야 한다 - 인자도, 횟수도.

    명시된 source가 detect보다 우선한다(Sprint107과 같다). 화면에서
    "자동"을 고른 사람은 폴더에 뭐가 있든 자동을 기대한다.
    """

    resolved = source or detect_source(project_path)

    if resolved not in SOURCES:
        raise VoiceResolveError(
            f"알 수 없는 음성 출처입니다: {resolved}. "
            f"{', '.join(SOURCES)} 중 하나여야 합니다."
        )

    if resolved in PREPARED_SOURCES:
        verdict, detail = validate(scenes, project_path)

        if verdict == "ready":
            print("STEP03 RESOLVE - " + resolved)
            assemble(detail, project_path)

            return None

        print("STEP03 RESOLVE WARN - " + detail)

    # AUTO. step03은 수정되지 않았고, 여기서만 불린다.
    from app.steps import step03_tts

    return step03_tts.run(scenes, project_path)
