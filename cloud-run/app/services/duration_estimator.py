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

# output/ 아래 실제 생성된 프로젝트(Chirp3-HD-Aoede, scene 150개 /
# 영상 48개)의 mp3 실측 길이 대 정규화된 narration 글자수로 최소자승
# 회귀(intercept 없음)해서 구한 값. 영상 전체(voice.mp3) 단위로는
# 평균 절대오차 약 1.56초(중앙값 1.19초, 42초 안팎 영상 기준 약
# 3.6%) 수준이었다. tests/test_duration_estimator.py의
# TestCalibrationAgainstRealAudio가 실제 두 프로젝트로 이 값을 검증한다.
DEFAULT_CHARS_PER_SECOND = 5.3
SENTENCE_PAUSE_SECONDS = 0.08
COMMA_PAUSE_SECONDS = 0.02
TARGET_DURATION_SECONDS = 45.0

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


def duration_deviation(
    estimated_seconds: float,
    target: float = TARGET_DURATION_SECONDS,
) -> float:
    """예상 길이가 목표 길이 대비 얼마나 벗어났는지(초)를 반환합니다.
    양수면 목표보다 길고, 음수면 목표보다 짧습니다."""

    return estimated_seconds - target
