"""
Sprint53-2 - Duration Optimizer (실측 오디오 후처리 방식).

Chirp3-HD-Aoede는 같은 텍스트를 넣어도 합성 길이가 크게(실측 기준
±30%대) 달라지는 비결정적 음성이라, SSML/speaking_rate로 "합성 전에"
길이를 예측해 맞추는 방식은 신뢰할 수 없다는 게 실측으로 확인됐다.
그래서 이 모듈은 텍스트/SSML이 아니라, 이미 합성이 끝난 실제 scene
mp3 파일들의 ffprobe 실측 길이를 보고 마지막 scene의 오디오 파일
자체만 후처리한다. narration/script.json/Speech Normalization 결과는
전혀 건드리지 않는다 - 오직 audio/scenes/*.mp3만 다룬다.

- 43~47초: 아무 파일도 건드리지 않는다.
- 43초 미만: ffmpeg로 만든 무음을 마지막 scene 오디오 뒤에 이어붙여
  확장한다. 부자연스러운 긴 정적을 막기 위해 MAX_PAUSE_SECONDS를
  넘지 않는다.
- 47초 초과: ffmpeg atempo 필터로 마지막 scene 오디오만 아주 살짝
  (MIN_SPEAKING_RATE~MAX_SPEAKING_RATE, 최대 ±3%) 빠르게 만든다.
"""

import os
import subprocess

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

TARGET_DURATION_SECONDS = 45.0
TOLERANCE_SECONDS = 2.0
MIN_ACCEPTABLE_SECONDS = TARGET_DURATION_SECONDS - TOLERANCE_SECONDS
MAX_ACCEPTABLE_SECONDS = TARGET_DURATION_SECONDS + TOLERANCE_SECONDS

MIN_SPEAKING_RATE = 0.97
MAX_SPEAKING_RATE = 1.03

MAX_PAUSE_SECONDS = 3.0


def get_audio_duration(path: str) -> float:

    result = subprocess.run(
        [
            FFPROBE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
    )

    text = result.stdout.strip()

    if not text:
        return 0.0

    try:
        return float(text)
    except ValueError:
        return 0.0


def append_silence(audio_path: str, pause_seconds: float, output_path: str) -> str:
    """audio_path 뒤에 pause_seconds(clamp됨) 길이의 무음을 이어붙인
    새 파일을 output_path에 만든다. audio_path 자체는 건드리지 않는다."""

    clamped_pause = min(max(pause_seconds, 0.0), MAX_PAUSE_SECONDS)

    command = [
        FFMPEG, "-y",
        "-i", audio_path,
        "-f", "lavfi",
        "-t", f"{clamped_pause:.2f}",
        "-i", "anullsrc=r=44100:cl=mono",
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
        "-map", "[out]",
        "-c:a", "libmp3lame",
        output_path,
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(result.stderr)

    return output_path


def speed_up_audio(audio_path: str, rate: float, output_path: str) -> str:
    """audio_path를 rate배(clamp됨) 빠르게 만든 새 파일을 output_path에
    만든다. audio_path 자체는 건드리지 않는다."""

    clamped_rate = min(max(rate, MIN_SPEAKING_RATE), MAX_SPEAKING_RATE)

    command = [
        FFMPEG, "-y",
        "-i", audio_path,
        "-filter:a", f"atempo={clamped_rate:.4f}",
        "-c:a", "libmp3lame",
        output_path,
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(result.stderr)

    return output_path


def _calculate_speaking_rate(
    original_seconds: float,
    seconds_to_remove: float,
    min_rate: float = MIN_SPEAKING_RATE,
    max_rate: float = MAX_SPEAKING_RATE,
) -> float:

    if original_seconds <= 0 or seconds_to_remove <= 0:
        return 1.0

    target_seconds = max(original_seconds - seconds_to_remove, 0.1)
    rate = original_seconds / target_seconds

    return min(max(rate, min_rate), max_rate)


def _apply_uniform_rate_to_other_scenes(
    scene_audio_paths: list, durations: list, rate: float, current_total: float,
) -> float:
    """
    last scene 단독 보정(rate 계산/무음 패딩)만으로는 43~47초 범위에
    들어오지 못하는 극단적인 경우에만 호출되는 2차 패스(cascade).
    이미 처리된 마지막 scene은 다시 건드리지 않고, 나머지 scene 각각에
    동일한 rate(기존과 같은 MIN/MAX_SPEAKING_RATE 한도 안)만큼만 추가로
    적용해 총 길이를 더 좁힌다. 안전 한도(±3%, 3초)는 절대 넓히지 않고,
    "last scene 하나"가 아니라 "여러 scene에 나눠서" 적용해 같은 한도로
    더 큰 총합 보정을 만드는 것이 핵심이다.
    """

    new_total = current_total

    for path, original_duration in zip(scene_audio_paths[:-1], durations[:-1]):
        tmp_path = path + ".optimized.mp3"
        speed_up_audio(path, rate, tmp_path)
        os.replace(tmp_path, path)

        new_duration = original_duration / rate
        new_total = new_total - original_duration + new_duration

    return new_total


def optimize_scene_audio(
    scene_audio_paths: list,
    target_duration: float = TARGET_DURATION_SECONDS,
    tolerance: float = TOLERANCE_SECONDS,
) -> dict:
    """
    이미 합성된 scene mp3 파일 경로 리스트를 받아, 실제 합 길이가
    target_duration±tolerance(기본 45±2=43~47초)를 벗어나면 마지막
    파일을 in-place로 후처리한다. 파일 개수/순서는 바꾸지 않는다.

    Sprint94 - ProductionProfile Duration Target Activation: target_
    duration/tolerance를 optional 파라미터로 받아 호출부(step03_tts.py)
    가 원하는 목표로 override할 수 있게 한다. 기본값은 기존 모듈 상수와
    동일해 파라미터 없이 호출하면 지금까지와 완전히 동일하다.

    Sprint74 - Duration Optimizer 안정화: 마지막 scene 하나에 대한
    보정(무음 패딩 최대 3초, 속도 조절 최대 ±3%)만으로는 격차가 큰
    실측 케이스(2026-07-10 E2E에서 43~47초 범위를 벗어난 채로 끝난
    실패 사례들)를 못 닫는 경우가 있었다. 안전 한도 자체를 넓히는 대신
    - 이미 Sprint53에서 오디오 품질 저하를 막기 위해 의도적으로 정한
    한도이므로 - 같은 한도를 마지막 scene 외 나머지 scene에도 나눠서
    적용해(2차 패스) 총 보정량을 늘린다. 1차 패스(마지막 scene만)로
    이미 범위 안에 들어오면 2차 패스는 발동하지 않는다.
    """

    min_acceptable = target_duration - tolerance
    max_acceptable = target_duration + tolerance

    if not scene_audio_paths:
        return {"action": "none", "original_total": 0.0, "final_total": 0.0}

    durations = [get_audio_duration(path) for path in scene_audio_paths]
    total = sum(durations)

    if min_acceptable <= total <= max_acceptable:
        return {"action": "none", "original_total": total, "final_total": total}

    last_path = scene_audio_paths[-1]
    last_duration = durations[-1]
    tmp_path = last_path + ".optimized.mp3"

    if total < min_acceptable:
        pause_seconds = min(
            max(target_duration - total, 0.0),
            MAX_PAUSE_SECONDS,
        )
        append_silence(last_path, pause_seconds, tmp_path)
        os.replace(tmp_path, last_path)

        final_total = total + pause_seconds
        result = {
            "action": "expand",
            "original_total": total,
            "final_total": final_total,
            "pause_seconds": pause_seconds,
            "secondary_adjustment": False,
        }

        if final_total < min_acceptable:
            result["final_total"] = _apply_uniform_rate_to_other_scenes(
                scene_audio_paths, durations, MIN_SPEAKING_RATE, final_total,
            )
            result["secondary_adjustment"] = True

        return result

    seconds_to_remove = total - target_duration
    rate = _calculate_speaking_rate(last_duration, seconds_to_remove)
    speed_up_audio(last_path, rate, tmp_path)
    os.replace(tmp_path, last_path)

    new_last_duration = last_duration / rate
    final_total = total - last_duration + new_last_duration

    result = {
        "action": "contract",
        "original_total": total,
        "final_total": final_total,
        "speaking_rate": rate,
        "secondary_adjustment": False,
    }

    if final_total > max_acceptable:
        result["final_total"] = _apply_uniform_rate_to_other_scenes(
            scene_audio_paths, durations, MAX_SPEAKING_RATE, final_total,
        )
        result["secondary_adjustment"] = True

    return result
