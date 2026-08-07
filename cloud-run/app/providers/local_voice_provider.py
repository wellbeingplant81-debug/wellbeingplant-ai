"""
Sprint151 - 내 PC의 목소리로 scene 음성을 만든다 (Epic 57, Phase 2).

돈이 들지 않는 제작의 소리 쪽이다. TTS를 부르지 않고, 사람이 미리
녹음해 둔 파일을 엔진이 쓰는 자리에 놓는다.

왜 낱말이 아니라 번호로 고르는가
--------------------------------
그림은 낱말이 겹치는 것을 골라도 된다(Sprint150). 조금 안 맞는
그림은 어색할 뿐이다.

목소리는 다르다. 3번 scene에 2번 나레이션이 들어가면 자막과 소리가
서로 다른 말을 하고, 그것은 어색한 것이 아니라 망가진 것이다. 이
저장소는 이미 그 결함을 겪었다 - Sprint146의 자막 어긋남은 두 목록을
서로 다른 차례로 zip한 데서 나왔다.

그래서 나레이션 글로 닮은 파일을 찾지 않는다. 파일 이름에 있는
번호만 읽는다.

    scene1.wav   1.wav   01_인사.wav   나레이션-4.wav

없으면 없다고 말한다. 다른 번호를 대신 주지 않고, TTS로 넘어가지도
않는다 - "비용 0원"이라고 해 놓고 조용히 Google을 부르면 그때부터
돈이 든다.

놓는 자리와 포맷
----------------
audio_policy가 정한다. scene{N}.wav, 24kHz mono PCM.

밖에서 온 44.1kHz 스테레오를 그대로 두면 뒤 단계의 concat이 전체를
리샘플한다 - audio_policy가 있는 이유가 "혹시 다른 소스가 섞여
들어와도 파이프라인 전체가 한 포맷으로 수렴한다"이고, 사람이 녹음한
파일이야말로 그 다른 소스다.

길이는 손대지 않는다. 재기만 한다. 늘리거나 자르는 것은 자동 수정이고,
어디가 경계인지 우리가 알 수 없다.
"""

import os
import re
import subprocess

from app.services import (
    audio_policy, duration_estimator, duration_optimizer, local_library,
)

FFMPEG = "ffmpeg"

# 받아 주는 것. 사양이 정한 둘이다.
SUPPORTED_SUFFIXES = (".wav", ".mp3")

# 낱말 끝의 숫자. "scene1" -> 1, "01" -> 1, "4" -> 4.
#
# local_library는 "scene1.wav"를 ["scene1"]로 끊는다 - 글자와 숫자
# 사이에는 구분자가 없기 때문이다. 그래서 낱말 전체가 숫자인 것만
# 보면 가장 흔한 이름을 놓친다.
#
# 끝자리만 읽으므로 "scene10"은 10이지 1이 아니고, "202401"도 1이
# 아니다 - 앞자리를 버리지 않는다.
_NUMBER = re.compile(r"(\d+)$")


class LocalVoiceUnavailable(RuntimeError):
    """내 PC 음성으로는 이 scene을 채울 수 없다.

    몇 번 scene이 왜 안 되는지 적는다 - 사람이 그 파일만 넣으면
    되는 일이다."""


def scene_number(output_file: str):
    """
    놓을 자리의 이름에서 scene 번호를 읽는다.

    generate_voice는 나레이션 글과 놓을 자리만 받는다(google_tts_
    provider와 같은 모양이다). 번호는 그 자리 이름이 들고 있다 -
    audio_policy.scene_audio_filename이 지은 이름이므로 우리가 지은
    규칙을 우리가 되읽는 것이다.
    """

    stem = os.path.splitext(os.path.basename(output_file or ""))[0]
    found = _NUMBER.search(stem)

    return int(found.group(1)) if found else None


def find(project_path: str, number: int):
    """
    그 번호의 음성 파일. 없으면 None.

    이름에 그 번호가 낱말로 들어 있는 것만 본다. 여러 개면 경로 순으로
    첫 번째다 - local_library.search가 이미 그렇게 정렬한다.
    """

    if number is None:
        return None

    index = local_library.load(project_path)

    for item in index.get("items") or []:
        if item.get("kind") != local_library.VOICE:
            continue

        if not item.get("name", "").lower().endswith(SUPPORTED_SUFFIXES):
            continue

        for tag in item.get("tags") or []:
            matched = _NUMBER.search(tag)

            if matched and int(matched.group(1)) == number:
                return item

    return None


def _normalize(source: str, target: str) -> None:
    """
    정책 포맷(24kHz mono PCM)으로 맞춰 넣는다.

    길이는 손대지 않는다 - 샘플레이트와 채널, 코덱만 맞춘다. 입력이
    이미 정책과 같으면 ffmpeg는 리샘플러를 태우지 않으므로 추가 손실이
    없다(audio_policy 참고).

    ffmpeg는 UTF-8로 말하는데 Windows의 기본값은 cp949다. 한국어 파일
    이름이 섞이면 stderr를 읽다가 죽으므로 UTF-8로 읽는다.
    """

    os.makedirs(os.path.dirname(target), exist_ok=True)

    result = subprocess.run(
        [FFMPEG, "-y", "-i", source] + audio_policy.pcm_output_args()
        + [target],
        capture_output=True, encoding="utf-8", errors="replace",
    )

    if result.returncode != 0 or not os.path.exists(target):
        raise LocalVoiceUnavailable(
            f"음성을 읽지 못했습니다: {os.path.basename(source)}. "
            f"{(result.stderr or '').strip()[-200:]}"
        )


def _require_playable(source: str, target: str) -> float:
    """
    재생할 수 있는지 본다. 길이가 0이면 놓아 봐야 렌더에서 죽는다.

    여기서 거절하면 사람은 파일을 고쳐서 다시 넣으면 된다. 반쯤 된
    것을 남기지 않는다 - 남으면 렌더 검사가 "있다"고 판단한다.
    """

    seconds = duration_optimizer.get_audio_duration(target)

    if seconds <= 0:
        os.remove(target)
        raise LocalVoiceUnavailable(
            f"재생할 수 없는 음성입니다: {os.path.basename(source)}. "
            "길이를 읽지 못했습니다."
        )

    return seconds


def generate_voice(text: str, output_file: str) -> str:
    """
    그 scene의 음성을 자리에 놓는다. 만들지 않는다 - 고를 뿐이다.

    이름이 generate_voice인 것은 google_tts_provider·elevenlabs_
    provider와 같은 자리에 꽂히기 때문이다. 하는 일은 "고르기"이고,
    그 사실은 이 설명이 든다.
    """

    number = scene_number(output_file)

    if number is None:
        raise LocalVoiceUnavailable(
            f"어느 scene의 음성인지 알 수 없습니다: {output_file}"
        )

    # audio/scenes/scene{N}.wav 에서 셋 위가 프로젝트다.
    project_path = os.path.dirname(
        os.path.dirname(os.path.dirname(output_file))
    )

    index = local_library.load(project_path)

    if not (index.get("items") or []):
        raise LocalVoiceUnavailable(
            "내 PC 자료 목록이 비어 있습니다. 폴더를 먼저 훑으십시오."
        )

    picked = find(project_path, number)

    if picked is None:
        raise LocalVoiceUnavailable(
            f"Scene {number}의 음성이 없습니다. voice 폴더에 이름이 "
            f"{number}번을 가리키는 파일(scene{number}.wav 등)을 "
            "넣으십시오."
        )

    _normalize(picked["path"], output_file)
    seconds = _require_playable(picked["path"], output_file)

    # 나레이션이 말하는 길이와 얼마나 다른가. 고치지 않는다 - 사람이
    # 다시 녹음할지 정할 수 있게 알려만 준다. 예상값은 Duration Gate가
    # 쓰는 그 estimator다.
    expected = duration_estimator.estimate_duration(text or "")

    print(f"STEP03 LOCAL VOICE - scene{number} · {picked['name']} · "
          f"{seconds:.1f}초 (나레이션 예상 {expected:.1f}초)")

    return output_file
