"""
Sprint53-4 - Duration Gate.

TTS를 부르기 전, AI Writer가 만든 narration의 예상 길이(Duration
Estimator)가 43~47초 범위인지 먼저 확인한다. 범위를 벗어나면 Writer를
다시 호출해 재생성한다(최대 max_attempts회). 실제 오디오 합성 없이
텍스트만으로 판단하므로 TTS 비용은 들지 않는다.

Duration Optimizer(Sprint53-2, TTS 합성 후 오디오 후처리)는 이 게이트를
통과한 대본의 미세한 오차(±3초/±3%)만 다듬는 최후 수단이다 - Writer의
큰 편차 자체는 이 게이트가 막는다.
"""

from app.services.duration_estimator import (
    DEFAULT_CHARS_PER_SECOND,
    estimate_script_duration,
)
from app.services.script_service import generate_script

MIN_ACCEPTABLE_SECONDS = 43.0
MAX_ACCEPTABLE_SECONDS = 47.0
MAX_ATTEMPTS = 3


def _is_within_range(
    estimated: float,
    min_acceptable: float,
    max_acceptable: float,
) -> bool:
    return min_acceptable <= estimated <= max_acceptable


def _build_retry_feedback(
    estimated_seconds: float,
    target_duration: float,
    chars_per_second: float = DEFAULT_CHARS_PER_SECOND,
) -> str:
    """
    Sprint69-2 - Duration Gate Adaptive Retry. 직전 시도의
    estimated_seconds가 target_duration보다 얼마나 짧거나 길었는지를
    duration_estimator와 같은 계수(chars_per_second)로 글자 수 차이로
    환산해, 다음 Writer 호출에 줄 구체적인 한국어 피드백 문구를
    만든다. Writer가 "그냥 다시 써보는" 랜덤 재시도가 아니라, 부족/
    초과분을 알고 조정할 수 있게 하는 것이 목적이다.
    """

    seconds_diff = target_duration - estimated_seconds
    chars_diff = round(abs(seconds_diff) * chars_per_second)

    if seconds_diff > 0:
        return (
            f"[재시도 피드백] 이전 시도는 예상 {estimated_seconds:.1f}초로 "
            f"목표({target_duration:.0f}초)보다 약 {seconds_diff:.1f}초 짧았습니다. "
            f"narration 전체를 지금보다 약 {chars_diff}자 더 길게 작성하세요."
        )

    return (
        f"[재시도 피드백] 이전 시도는 예상 {estimated_seconds:.1f}초로 "
        f"목표({target_duration:.0f}초)보다 약 {abs(seconds_diff):.1f}초 길었습니다. "
        f"narration 전체를 지금보다 약 {chars_diff}자 더 짧게 작성하세요."
    )


def generate_script_within_duration(
    topic: str,
    target_duration: int = 45,
    scene_count: int = 6,
    max_attempts: int = MAX_ATTEMPTS,
    min_acceptable: float = MIN_ACCEPTABLE_SECONDS,
    max_acceptable: float = MAX_ACCEPTABLE_SECONDS,
    generate_fn=generate_script,
    estimate_fn=estimate_script_duration,
) -> dict:
    """
    generate_fn()으로 대본을 생성하고 estimate_fn()으로 예상 길이를
    계산해 min_acceptable~max_acceptable 범위인지 확인한다. 범위를
    벗어나면 최대 max_attempts회까지 다시 생성한다. 어떤 시도도 범위
    안에 들지 못하면, 목표(min/max 중앙값)에 가장 가까웠던 시도를
    반환한다 - 파이프라인이 무조건 멈추지 않도록 하기 위함이다.

    Sprint69-2 - Adaptive Retry: 재시도마다 직전 시도의 estimated_
    seconds를 기반으로 만든 구체적인 피드백(_build_retry_feedback)을
    generate_fn에 넘긴다 - 이전에는 매 시도가 동일한 프롬프트로 그냥
    다시 뽑는 것이라 개선 신호가 없었다. 첫 시도는 피드백이 없다(빈
    문자열). 반환 dict에는 target(=min/max 중앙값) 대비 최종 채택된
    시도의 shortfall_seconds(양수=부족, 음수=초과)를 항상 포함해,
    실패 시 QA 로그가 부족 시간을 명확히 남길 수 있게 한다.
    """

    target = (min_acceptable + max_acceptable) / 2
    best = None
    retry_feedback = ""

    for attempt in range(1, max_attempts + 1):

        result = generate_fn(
            topic=topic,
            target_duration=target_duration,
            scene_count=scene_count,
            retry_feedback=retry_feedback,
        )

        scenes = result["data"]["scenes"]
        estimated = estimate_fn(scenes)
        passed = _is_within_range(estimated, min_acceptable, max_acceptable)

        candidate = {
            "result": result,
            "estimated_seconds": estimated,
            "attempts": attempt,
            "passed": passed,
            "shortfall_seconds": target - estimated,
        }

        if passed:
            return candidate

        retry_feedback = _build_retry_feedback(estimated, target_duration)

        if best is None or abs(estimated - target) < abs(best["estimated_seconds"] - target):
            best = candidate

    return best
