"""
Sprint53 - Duration Estimator.

스크립트(narration)를 실제로 합성하지 않고도, Google TTS가 만들어낼
예상 길이를 추정합니다. AI를 다시 호출하지 않는 순수 규칙 기반
계산이며, speech_normalizer와 같은 정규화 규칙을 내부적으로 재사용해
"2번"처럼 숫자+단위 표기가 실제로는 "두 번"(더 긴 발화)으로 읽힌다는
점까지 반영합니다.

DEFAULT_CHARS_PER_SECOND / *_PAUSE_SECONDS 상수는 실제 생성된 TTS
오디오(Chirp3-HD-Aoede)로 보정된 값입니다 - Sprint53-1 계산 근거는
duration_estimator 캘리브레이션 스크립트 실행 결과를 참고하세요.
"""

import re

from app.services.speech_normalizer import normalize_for_speech

# 실제 Google Cloud TTS(ko-KR-Chirp3-HD-Aoede)를 호출해서 얻은 값이다
# (.env의 TTS_PROVIDER가 한동안 "elevenlabs"로 잘못 설정돼 있던 걸
# Sprint53-1 도중 발견하고 "google"로 고친 뒤 재측정했다 - 이전에
# ElevenLabs 오디오로 계산했던 계수는 이 음성엔 맞지 않아 폐기).
#
# 실제 대본 3개(scene 18개, output/20260706_164907·20260707_161744·
# 20260707_155319의 narration을 그대로 재사용) 각각을 Google TTS로
# 합성해 ffprobe로 실측한 뒤, 정규화된 narration 글자수 대비 최소자승
# 회귀(intercept 없음)로 구했다. comma_pause는 표본에서 통계적으로
# 0에 가까워(오히려 살짝 음수) 0으로 고정했다. 영상 전체 단위 평균
# 절대오차는 약 1.15초(40~43초대 영상 기준 약 2.9%)였다.
# tests/test_duration_estimator.py의 TestCalibrationAgainstRealAudio가
# 이 세 대본으로 값을 검증한다.
DEFAULT_CHARS_PER_SECOND = 5.93
SENTENCE_PAUSE_SECONDS = 0.53
COMMA_PAUSE_SECONDS = 0.0
TARGET_DURATION_SECONDS = 45.0

# Sprint97 - ElevenLabs 실측 계수. Duration Gate/script_service가 항상
# DEFAULT_CHARS_PER_SECOND(Chirp)로 narration을 추정해, 더 느리게
# 말하는 ElevenLabs(ProductionProfile "upload"의 tts_provider)에서는
# 목표(55±2초)보다 실제 오디오가 훨씬 길게(2026-07-13 Production QA:
# 68.68초) 나오는 문제가 있었다. 이 값은 그 실측 E2E(output/
# 20260713_084207, narration 341자/문장 14개, Duration Optimizer 후처리
# 전 실측 audio 합 70.68초)로 역산한 것이다. Chirp 계수(Sprint53-1)처럼
# narration 3개로 회귀시킨 값이 아니라 표본 1개짜리 역산이므로, 추가
# 실측이 쌓이면 갱신이 필요하다.
ELEVENLABS_CHARS_PER_SECOND = 5.39

_NON_SPEECH_PATTERN = re.compile(r"[\s.,!?]+")
_SENTENCE_END_PATTERN = re.compile(r"[.!?]")


def estimate_duration(
    text: str,
    chars_per_second: float = DEFAULT_CHARS_PER_SECOND,
    sentence_pause: float = SENTENCE_PAUSE_SECONDS,
    comma_pause: float = COMMA_PAUSE_SECONDS,
) -> float:
    """
    한 문자열(narration 한 덩어리)의 예상 TTS 발화 길이(초)를 계산합니다.
    입력 text는 변경하지 않는 순수 함수입니다.
    """

    if not text:
        return 0.0

    normalized = normalize_for_speech(text)

    # 문장부호(.,!?)와 공백은 실제로 발화되는 글자가 아니라 pause로
    # 따로 계산하므로, 글자수 집계에서는 제외한다.
    effective_chars = len(_NON_SPEECH_PATTERN.sub("", normalized))
    base_seconds = effective_chars / chars_per_second

    sentence_count = len(_SENTENCE_END_PATTERN.findall(normalized))
    comma_count = normalized.count(",")

    pause_seconds = (
        sentence_count * sentence_pause
        + comma_count * comma_pause
    )

    return base_seconds + pause_seconds


def estimate_script_duration(
    scenes: list,
    chars_per_second: float = DEFAULT_CHARS_PER_SECOND,
    sentence_pause: float = SENTENCE_PAUSE_SECONDS,
    comma_pause: float = COMMA_PAUSE_SECONDS,
) -> float:
    """scene 리스트(script.json의 "scenes")의 narration을 모두 합친
    총 예상 발화 길이(초)를 계산합니다."""

    if not scenes:
        return 0.0

    return sum(
        estimate_duration(
            scene["narration"],
            chars_per_second=chars_per_second,
            sentence_pause=sentence_pause,
            comma_pause=comma_pause,
        )
        for scene in scenes
    )


def chars_per_second_for_provider(tts_provider: str = None) -> float:
    """ProductionProfile의 tts_provider 값("chirp"/"elevenlabs" - 실제
    TTS 라우팅과 동일한 문자열)에 맞는 chars_per_second 계수를 고른다.
    None이거나 "elevenlabs"가 아니면 기존 DEFAULT_CHARS_PER_SECOND
    (Chirp)를 그대로 반환한다 - 완전히 하위 호환."""

    if tts_provider == "elevenlabs":
        return ELEVENLABS_CHARS_PER_SECOND
    return DEFAULT_CHARS_PER_SECOND


def duration_deviation(
    estimated_seconds: float,
    target: float = TARGET_DURATION_SECONDS,
) -> float:
    """예상 길이가 목표 길이 대비 얼마나 벗어났는지(초)를 반환합니다.
    양수면 목표보다 길고, 음수면 목표보다 짧습니다."""

    return estimated_seconds - target
