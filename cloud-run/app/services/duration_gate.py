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

from app.services.duration_estimator import estimate_script_duration
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
    """

    target = (min_acceptable + max_acceptable) / 2
    best = None

    for attempt in range(1, max_attempts + 1):

        result = generate_fn(
            topic=topic,
            target_duration=target_duration,
            scene_count=scene_count,
        )

        scenes = result["data"]["scenes"]
        estimated = estimate_fn(scenes)
        passed = _is_within_range(estimated, min_acceptable, max_acceptable)

        candidate = {
            "result": result,
            "estimated_seconds": estimated,
            "attempts": attempt,
            "passed": passed,
        }

        if passed:
            return candidate

        if best is None or abs(estimated - target) < abs(best["estimated_seconds"] - target):
            best = candidate

    return best
