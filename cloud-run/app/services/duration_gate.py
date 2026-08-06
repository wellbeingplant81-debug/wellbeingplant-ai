"""
Sprint53-4 - Duration Gate.

TTS를 부르기 전, AI Writer가 만든 narration의 예상 길이(Duration
Estimator)가 43~47초 범위인지 먼저 확인한다. 범위를 벗어나면 Writer를
다시 호출해 재생성한다(최대 max_attempts회). 실제 오디오 합성 없이
텍스트만으로 판단하므로 TTS 비용은 들지 않는다.

Duration Optimizer(Sprint53-2, TTS 합성 후 오디오 후처리)는 이 게이트를
통과한 대본의 미세한 오차(±3초/±3%)만 다듬는 최후 수단이다 - Writer의
큰 편차 자체는 이 게이트가 막는다.

Sprint95 - Topic Fidelity. 이 게이트가 보는 것이 하나 늘었다. 길이가
맞아도 주제를 벗어났으면 통과가 아니다.

재시도 루프를 따로 만들지 않고 여기에 얹은 이유는 비용이다. 게이트를
하나 더 쌓으면 최악의 경우 Gemini 호출이 3회에서 9회로 늘어난다.
한 번 만든 대본을 두 기준으로 함께 보면 3회 그대로다.
"""

from app.services import topic_fidelity
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
    fidelity_fn=topic_fidelity.check,
) -> dict:
    """
    generate_fn()으로 대본을 생성하고 estimate_fn()으로 예상 길이를
    계산해 min_acceptable~max_acceptable 범위인지 확인한다. 범위를
    벗어나면 최대 max_attempts회까지 다시 생성한다. 어떤 시도도 범위
    안에 들지 못하면, 목표(min/max 중앙값)에 가장 가까웠던 시도를
    반환한다 - 파이프라인이 무조건 멈추지 않도록 하기 위함이다.
    """

    # Sprint95 - Writer를 부르기 전에 주제부터 본다. 빈 주제를 받은
    # 모델은 반드시 무언가를 지어내고, 그 대본으로 이미지 6장과 음성과
    # 영상이 만들어진다 - 아무도 시키지 않은 주제로.
    topic_fidelity.validate_topic(topic)

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
        within_range = _is_within_range(estimated, min_acceptable, max_acceptable)
        fidelity = fidelity_fn(topic, result["data"])

        candidate = {
            "result": result,
            "estimated_seconds": estimated,
            "attempts": attempt,
            "duration_passed": within_range,
            "topic_fidelity": fidelity,
            "passed": within_range and fidelity["passed"],
        }

        if candidate["passed"]:
            return candidate

        # 어느 것도 통과하지 못하면 가장 나은 것을 돌려준다 -
        # 파이프라인이 통째로 멈추지는 않게 한다. 다만 주제를 지킨
        # 대본이 길이만 맞는 대본보다 낫다. 주제를 벗어난 영상은
        # 길이가 정확해도 쓸 수 없기 때문이다.
        if best is None or _is_better(candidate, best, target):
            best = candidate

    return best


def _is_better(candidate: dict, best: dict, target: float) -> bool:
    """주제 충실도가 먼저, 그다음이 목표 길이와의 거리."""

    candidate_topic = candidate["topic_fidelity"]["passed"]
    best_topic = best["topic_fidelity"]["passed"]

    if candidate_topic != best_topic:
        return candidate_topic

    return (
        abs(candidate["estimated_seconds"] - target)
        < abs(best["estimated_seconds"] - target)
    )
