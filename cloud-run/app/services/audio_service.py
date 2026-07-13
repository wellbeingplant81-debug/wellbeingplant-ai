import os
import subprocess

from app.services.bgm_service import select_bgm
from app.services.duration_optimizer import get_audio_duration

# Sprint54-1 - BGM 볼륨/페이드 상수. narration은 그대로(0dB), BGM은
# 충분히 낮춰서 narration을 절대 가리지 않게 한다.
#
# Sprint97 - narration 전달력을 더 우선하기 위해 기존 -28dB 대비 약
# 10% 더 낮춘다(-28.0 * 1.10 = -30.8). 믹싱 구조(ducking/fade)는
# 그대로 두고 gain 값만 조정한다.
NARRATION_VOLUME_DB = 0.0
BGM_VOLUME_DB = -30.8
BGM_FADE_IN_SECONDS = 0.5
BGM_FADE_OUT_SECONDS = 1.0

# Sprint54-2 - BGM Ducking. ffmpeg sidechaincompress로 narration을
# 사이드체인 삼아 BGM만 실시간으로 누른다 - narration 구간을 텍스트/
# 타임스탬프로 미리 검출하지 않고, 오디오 레벨 자체가 트리거가 되므로
# scene 경계나 문장 길이와 무관하게 항상 정확하다.
#
# 값은 실제 narration(output/20260708_115613/audio/voice.mp3, 실측
# mean -21.9dB / max -1.5dB)과 실제 BGM 트랙으로 튜닝했다:
# threshold=0.15(~-16.5dB)는 조용한 구간(무음에 가까움)에는 반응하지
# 않고 실제 말하는 구간에서만 켜지며, ratio=8/attack=20ms로 빠르게
# 눌렀다가 release=400ms로 자연스럽게 복귀한다. makeup=1(추가 부스트
# 없음 - BGM을 더 키우지 않고 누르기만 한다).
DUCK_THRESHOLD = 0.15
DUCK_RATIO = 8
DUCK_ATTACK_MS = 20
DUCK_RELEASE_MS = 400
DUCK_MAKEUP = 1


def concat_scene_audio(scene_audio_paths, output_file):

    ffmpeg = "ffmpeg"

    list_file = os.path.join(
        os.path.dirname(output_file),
        "scene_audio_list.txt",
    )

    with open(
        list_file,
        "w",
        encoding="utf-8",
    ) as f:

        for path in scene_audio_paths:
            escaped = os.path.abspath(path).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_file,
        "-c:a",
        "libmp3lame",
        output_file,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    print(result.stderr)

    os.remove(list_file)

    if result.returncode != 0:
        raise Exception(result.stderr)

    return output_file


def mix_audio(project_path: str, bgm_category: str = None):

    ffmpeg = "ffmpeg"

    voice = os.path.join(
        project_path,
        "audio",
        "voice.mp3",
    )

    bgm = select_bgm(bgm_category)

    output = os.path.join(
        project_path,
        "audio",
        "final_audio.mp3",
    )

    # Sprint53 Duration Optimizer가 이미 확정한 실제 narration 길이에
    # 맞춰 BGM fade-out 시작 시점을 계산한다 - 영상 길이가 더 이상
    # 고정 45초가 아니므로(43~47초) 하드코딩된 값을 쓸 수 없다.
    voice_duration = get_audio_duration(voice)
    fade_out_start = max(voice_duration - BGM_FADE_OUT_SECONDS, 0.0)

    command = [
        ffmpeg,
        "-y",
        "-i",
        voice,
        "-stream_loop",
        "-1",
        "-i",
        bgm,
        "-filter_complex",
        (
            f"[1:a]volume={BGM_VOLUME_DB}dB,"
            f"afade=t=in:st=0:d={BGM_FADE_IN_SECONDS},"
            f"afade=t=out:st={fade_out_start:.3f}:d={BGM_FADE_OUT_SECONDS}"
            "[bgm];"
            f"[0:a]volume={NARRATION_VOLUME_DB}dB[voice];"
            # Sprint54-2 - narration을 사이드체인으로 써서 BGM만 누른다.
            # narration 자체는 이 필터의 대상이 아니므로(사이드체인 입력일
            # 뿐) 그대로 유지된다.
            f"[bgm][voice]sidechaincompress=threshold={DUCK_THRESHOLD}:"
            f"ratio={DUCK_RATIO}:attack={DUCK_ATTACK_MS}:"
            f"release={DUCK_RELEASE_MS}:makeup={DUCK_MAKEUP}[bgm_ducked];"
            "[voice][bgm_ducked]"
            # normalize=0 필수: amix의 기본값(normalize=1)은 스트림 수로
            # 나눠서(2개 입력이면 -6dB) narration까지 조용히 더 줄여버린다 -
            # "음성이 항상 최우선"이라는 원칙과 NARRATION_VOLUME_DB=0의
            # 의미가 깨진다. 실측(volumedetect)으로 확인: normalize=0
            # 없이는 narration max_volume이 -1.5dB -> -7.6dB로 떨어졌다.
            "amix=inputs=2:duration=first:dropout_transition=2:normalize=0"
        ),
        "-c:a",
        "mp3",
        output,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    print(result.stderr)

    if result.returncode != 0:
        raise Exception(result.stderr)

    return output