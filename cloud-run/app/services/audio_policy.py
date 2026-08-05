"""
Sprint63 - Master Quality Audio.

나레이션 오디오 파이프라인의 단일 품질 정책. 샘플레이트/채널/중간
포맷/코덱/파일명은 전부 여기서만 정의하고, TTS provider부터 최종 mux
까지 모든 모듈이 이 값을 참조한다. 이전에는 같은 결정이 8개 모듈에
문자열로 흩어져 있어서(scene{n}.mp3, voice.mp3, final_audio.mp3,
libmp3lame, anullsrc=r=44100 ...) 어디 한 곳만 바꾸면 조용히 깨졌다.

왜 무손실 PCM인가
-----------------
Sprint62까지 나레이션은 최종 MP4에 닿기까지 최대 5번 손실 인코딩을
거쳤고, 그중 4번이 32kbps였다:

    Google TTS(MP3 32kbps)
      -> Duration Optimizer(libmp3lame, 기본값이 32kbps로 떨어짐)
      -> concat_scene_audio(libmp3lame, 동일)
      -> mix_audio(-c:a mp3, 동일)
      -> 최종 mux(AAC)

libmp3lame은 비트레이트를 지정하지 않으면 24kHz mono 입력에서 32kbps로
내려간다(실측). 즉 중간 단계마다 32kbps 격자로 반복 재양자화됐다.

중간 산출물은 최종 AAC 인코딩 직전에만 쓰이고 버려지므로 파일 크기는
아무 의미가 없다. 그래서 전 구간을 무손실 PCM으로 유지하고, 손실
인코딩은 최종 MP4의 AAC 한 번만 남긴다.

왜 24kHz인가
------------
실측(2026-08-05, ko-KR-Chirp3-HD-Aoede, 동일 문장, 99.9% spectral
rolloff):

    MP3(기본)         5,848Hz
    LINEAR16(24kHz)   9,152Hz
    LINEAR16(48kHz)   7,746Hz,  E(>11kHz) 0.002%

sample_rate_hertz=48000을 요청하면 Google이 48kHz로 돌려주긴 하지만
11kHz 위에 에너지가 사실상 없다 - Chirp3-HD의 네이티브 대역이 24kHz라
서버가 업샘플링해 줄 뿐이다. 바이트만 두 배가 되고 정보량은 늘지
않으므로 네이티브 24kHz를 그대로 쓴다.
"""


# --- 나레이션 (파이프라인 내부, 무손실) ---------------------------------

# Chirp3-HD 네이티브 샘플레이트. 이보다 높게 요청해도 실제 대역은 늘지
# 않는다(위 실측 참고).
NARRATION_SAMPLE_RATE_HZ = 24000

NARRATION_CHANNELS = 1

NARRATION_EXTENSION = ".wav"

NARRATION_PCM_CODEC = "pcm_s16le"


# --- 배포 (최종 MP4, 손실 인코딩 1회) -----------------------------------

# MP4 호환성 유지: 컨테이너/코덱 조합은 Sprint62 이전과 동일하다.
DELIVERY_AUDIO_CODEC = "aac"
DELIVERY_AUDIO_BITRATE = "192k"


# --- 파일명 (전부 NARRATION_EXTENSION에서 파생) -------------------------

VOICE_FILENAME = f"voice{NARRATION_EXTENSION}"

FINAL_AUDIO_FILENAME = f"final_audio{NARRATION_EXTENSION}"

SCENE_AUDIO_GLOB = f"scene*{NARRATION_EXTENSION}"


def scene_audio_filename(index: int) -> str:
    """scene 번호(1-base)에 해당하는 나레이션 파일명."""

    return f"scene{index}{NARRATION_EXTENSION}"


def pcm_output_args() -> list:
    """
    ffmpeg가 정책에 맞는 무손실 PCM을 쓰도록 하는 출력 인자.

    샘플레이트/채널을 명시하는 이유: 입력이 이미 정책과 같으면 ffmpeg는
    리샘플러를 아예 태우지 않으므로 추가 손실이 없고, 혹시 다른 소스가
    섞여 들어와도 파이프라인 전체가 한 포맷으로 수렴한다.
    """

    return [
        "-c:a", NARRATION_PCM_CODEC,
        "-ar", str(NARRATION_SAMPLE_RATE_HZ),
        "-ac", str(NARRATION_CHANNELS),
    ]


def silence_source() -> str:
    """
    무음 생성용 lavfi 소스 문자열. 나레이션과 샘플레이트/채널이 다르면
    concat 필터가 전체를 리샘플하므로 반드시 정책값과 맞춘다.
    """

    layout = "mono" if NARRATION_CHANNELS == 1 else "stereo"

    return f"anullsrc=r={NARRATION_SAMPLE_RATE_HZ}:cl={layout}"
