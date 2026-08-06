"""
Sprint73 - Intelligent Regeneration Engine의 결정 논리.

regeneration_service는 이미 "PASS한 scene은 건드리지 않고 FAIL한
scene만, 최대 3회까지" 재생성한다. 빠져 있던 것은 멈추는 법이다.

  - 비용 상한이 없었다. scene 6개면 최대 18번의 이미지 생성이 가능했고
    그걸 막는 것은 재시도 횟수뿐이었다.
  - 개선을 보지 않았다. 재생성이 품질을 떨어뜨려도 재시도 한도까지
    계속 돌았다. Imagen은 같은 프롬프트에도 매번 다른 그림을 그리므로
    나빠지는 쪽으로 굴러가는 일이 실제로 가능하다.
  - 왜 멈췄는지 남지 않았다.

이 모듈은 그 결정들만 담는다. 순수 함수뿐이라 실제 생성 없이 검증된다 -
멈추는 조건을 확인하는 데 Imagen을 부를 이유가 없다.
"""

from app.config import QUALITY_MAX_RETRY, REGENERATION_MAX_IMAGE_CALLS


# 스톡 scene은 재생성 대상이 아니다. Sprint40이 이 규칙을 세울 때 적은
# 근거는 "Pexels 실사진은 서로 다른 실존 인물이라 장면 간 동일 인물
# 평가를 통과할 수 없다"였다. Sprint73에서 그 근거가 더는 성립하지
# 않는다고 보고 규칙을 걷어냈다 - Character Consistency가 켜진 뒤로는
# 인물 scene이 애초에 스톡으로 가지 않으니까.
#
# 실제로 돌려 보니 결론은 같고 이유가 정반대였다. 사물 scene(오트밀
# 그릇, realism 20점)을 Imagen으로 다시 그리자 프롬프트에 없던 젊은
# 여성의 얼굴이 그릇 위로 들어왔다. 프롬프트는 "top-down view of a
# ceramic bowl"뿐이었다. 그 사람은 앵커 캐릭터와 다르므로
# character_consistency 95 -> 20, overall_quality 70 -> 60.
#
# 위험은 "스톡이 서로 다른 사람"이 아니라 "사물 scene을 Imagen에
# 맡기면 사람을 그려 넣는다"다. 규칙은 그대로 두고 근거만 바꾼다.
STOCK_PROVIDERS = frozenset({
    "pexels_image", "pexels_video", "pixabay_image", "pixabay_video",
})

# 이만큼은 올라야 "나아졌다"고 본다. Gemini 점수는 5~10점 단위로 움직이고
# 같은 이미지에도 흔들리므로(Sprint69 실측), 그보다 작은 변화로 예산을
# 계속 태우지 않는다.
MIN_IMPROVEMENT = 3.0

STOP_NOTHING_ELIGIBLE = "nothing_eligible"
STOP_BUDGET_EXHAUSTED = "budget_exhausted"
STOP_NO_IMPROVEMENT = "no_improvement"
STOP_NO_SUCCESSFUL_REGENERATION = "no_successful_regeneration"
STOP_REGRESSED = "regressed"

STOP_REASONS = (
    STOP_NOTHING_ELIGIBLE,
    STOP_BUDGET_EXHAUSTED,
    STOP_NO_IMPROVEMENT,
    STOP_NO_SUCCESSFUL_REGENERATION,
    STOP_REGRESSED,
)

_STOP_EXPLANATIONS = {
    STOP_NOTHING_ELIGIBLE: (
        "재생성할 scene이 없습니다 - 전부 통과했거나, 스톡이라 재생성이 "
        "의미 없거나, 재시도 한도에 도달했습니다."
    ),
    STOP_BUDGET_EXHAUSTED: (
        f"이미지 생성 예산({REGENERATION_MAX_IMAGE_CALLS}회)을 모두 "
        f"썼습니다. 남은 scene은 다음 실행으로 미룹니다."
    ),
    STOP_NO_IMPROVEMENT: (
        f"직전 사이클 대비 품질이 {MIN_IMPROVEMENT}점 이상 오르지 "
        f"않았습니다. 더 돌려도 나아진다는 근거가 없으므로 멈춥니다."
    ),
    STOP_NO_SUCCESSFUL_REGENERATION: (
        "이번 사이클에서 성공적으로 재생성된 scene이 하나도 없습니다."
    ),
    STOP_REGRESSED: (
        "재생성 결과가 직전보다 나빴습니다. 원본 이미지를 되돌리고 "
        "멈췄습니다 - 개선된 경우에만 유지합니다."
    ),
}


def explain_stop(reason: str) -> str:
    """중단 사유를 사람이 읽는 문장으로."""

    return _STOP_EXPLANATIONS.get(
        reason, f"알 수 없는 중단 사유입니다: {reason!r}",
    )


def regeneration_targets(evaluation, scenes_by_number, retry_counts) -> list:
    """
    이번 사이클에 재생성할 scene 번호. 순수 함수입니다.

    이 엔진의 첫 번째 원칙이 여기 있다 - regenerate 표시가 없는 scene은
    아예 후보가 되지 않는다. 통과한 그림을 다시 그리면 좋아질 수도
    있지만 나빠질 수도 있고, 돈은 확실히 든다.

    스톡 scene도 후보가 아니다 - 이유는 STOCK_PROVIDERS 주석에 있다.
    """

    scenes = (evaluation or {}).get("scenes") or []

    return [
        scene["scene"]
        for scene in scenes
        if scene.get("regenerate")
        and (scenes_by_number.get(scene["scene"], {}).get("provider")
             not in STOCK_PROVIDERS)
        and retry_counts.get(scene["scene"], 0) < QUALITY_MAX_RETRY
    ]


def apply_cost_budget(eligible: list, spent: int, budget: int):
    """
    남은 예산만큼만 자른다. 잘린 scene은 조용히 사라지지 않고
    dropped로 함께 돌아온다 - 로그에 남겨야 다음 실행에서 이어갈 수
    있다.

    반환값: (allowed, dropped)
    """

    remaining = max(0, budget - spent)

    return list(eligible[:remaining]), list(eligible[remaining:])


def cycle_quality(evaluation) -> float:
    """
    사이클끼리 비교할 하나의 숫자.

    두 부분으로 이루어진다. scene별 realism/composition의 평균과,
    영상 전체의 character_consistency다.

    Gemini의 종합 점수(overall_quality)를 그대로 쓰지 않는 이유는,
    거기에는 썸네일이나 훅처럼 재생성이 건드리지 않는 것들이 섞여
    있어 무엇이 나아졌는지 흐려지기 때문이다.

    Sprint73 - 원래는 scene 평균만 썼다. 그런데 그러면 목적 함수가
    재생성이 부수는 것을 보지 못한다. 실측에서 scene 평균은
    81.2 -> 83.8로 올랐는데 같은 사이클에 character_consistency가
    95 -> 20으로 무너졌고 overall_quality는 70 -> 60으로 떨어졌다.
    엔진은 이것을 +2.6점 개선으로 읽고 결과를 그대로 내보냈다.

    인물 일관성은 scene 하나가 어긋나면 영상 전체가 무너지는 성질이라
    scene 평균과 같은 무게를 준다. 이 비중은 측정으로 구한 최적값이
    아니라 판단이다 - 다만 어느 쪽으로 기울여도 위 사례는 걸러진다.
    """

    scenes = (evaluation or {}).get("scenes") or []

    if not scenes:
        return 0.0

    total = sum(
        scene.get("realism_score", 0) + scene.get("composition_score", 0)
        for scene in scenes
    )
    scene_mean = total / (2 * len(scenes))

    consistency = ((evaluation or {}).get("scores") or {}).get(
        "character_consistency"
    )

    if consistency is None:
        return scene_mean

    return (scene_mean + consistency) / 2


def regressed(quality_before, quality_after) -> bool:
    """
    이번 사이클의 결과를 남길지 되돌릴지.

    재평가에 실패해 quality_after가 없으면 되돌린다. 좋아졌다는 근거가
    없는 결과를 근거 없이 남길 이유가 없다 - 되돌리면 최소한 직전까지
    확인된 상태로 돌아간다.
    """

    if quality_after is None:
        return True

    return quality_after < quality_before


def decide_continue(eligible, spent, previous_quality, current_quality) -> dict:
    """
    한 사이클을 더 돌지 말지. 순수 함수입니다.

    순서가 의미를 갖는다. 할 일이 없으면 예산이 남았는지 볼 필요가
    없고, 예산이 없으면 품질이 올랐는지는 소용없다.
    """

    if not eligible:
        return {"continue": False, "stop_reason": STOP_NOTHING_ELIGIBLE}

    if spent >= REGENERATION_MAX_IMAGE_CALLS:
        return {"continue": False, "stop_reason": STOP_BUDGET_EXHAUSTED}

    # 첫 사이클은 비교할 이전 값이 없다 - 일단 한 번은 돌아 봐야 한다.
    if previous_quality is None or current_quality is None:
        return {"continue": True, "stop_reason": None}

    if current_quality - previous_quality < MIN_IMPROVEMENT:
        return {"continue": False, "stop_reason": STOP_NO_IMPROVEMENT}

    return {"continue": True, "stop_reason": None}


def new_log() -> dict:
    """결정 로그를 시작한다."""

    return {
        "max_image_calls": REGENERATION_MAX_IMAGE_CALLS,
        "max_retry_per_scene": QUALITY_MAX_RETRY,
        "min_improvement": MIN_IMPROVEMENT,
        "cycles": [],
        "stop_reason": None,
        "stop_explanation": None,
        "total_image_calls": 0,
        "rendered": False,
    }


def record_cycle(log, cycle, targeted, dropped_for_budget, succeeded, failed,
                 quality_before, quality_after, spent, rolled_back=()) -> None:
    """사이클 하나가 무엇을 했고 무엇이 달라졌는지 남긴다.

    rolled_back은 다시 그렸다가 더 나빠져서 원본으로 되돌린 scene이다.
    succeeded와 겹칠 수 있다 - 생성은 성공했지만 남기지 않았다는 뜻이고,
    비용은 그대로 나갔으므로 둘 다 보여야 한다.
    """

    log["cycles"].append({
        "cycle": cycle,
        "targeted": list(targeted),
        "dropped_for_budget": list(dropped_for_budget),
        "succeeded": list(succeeded),
        "failed": list(failed),
        "rolled_back": list(rolled_back),
        "quality_before": quality_before,
        "quality_after": quality_after,
        "quality_delta": (
            None
            if quality_before is None or quality_after is None
            else quality_after - quality_before
        ),
        "spent": spent,
    })


def close_log(log, stop_reason, spent, rendered) -> None:
    """왜 멈췄는지, 얼마나 썼는지, 영상을 다시 만들었는지."""

    log["stop_reason"] = stop_reason
    log["stop_explanation"] = explain_stop(stop_reason)
    log["total_image_calls"] = spent
    log["rendered"] = rendered
