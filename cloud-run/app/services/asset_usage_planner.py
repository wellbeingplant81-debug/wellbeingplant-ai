"""
Sprint64-3 - Role metadata를 활용한 Asset Usage Planning 구조.

Scene당 여러 asset(Sprint62-4)에 붙은 role(Sprint64-2: environment/
subject/detail/transition)을 바탕으로, 각 asset이 scene duration 중
얼마나 차지해야 하는지(duration weighting)와 어떤 Ken Burns 모션이
어울리는지(motion_hint)를 계산합니다.

이번 스프린트는 계획 산출물만 만듭니다 - video_builder.py/kenburns.py
는 전혀 수정하지 않으며, 이 모듈의 결과를 아직 아무 곳에서도
소비하지 않습니다(향후 스프린트에서 신중히 연결). 순수 함수입니다 -
파일 접근, 렌더링, 부수효과 없음.
"""

# role별 duration 가중치. 합이 아니라 "비율"로만 쓰이므로 절대값
# 자체는 의미 없고, 서로 간 상대적 크기만 의미를 가진다.
ROLE_DURATION_WEIGHTS = {
    "environment": 1.2,  # 도입부 - 살짝 길게
    "subject": 1.0,       # 기준
    "detail": 0.8,        # 살짝 짧게
    "transition": 0.6,    # 브릿지 컷 - 가장 짧게
}

# role이 없거나(하위 호환) 알 수 없는 값이면 이 가중치를 쓴다 -
# 모든 asset이 이 값이면 결과는 기존 균등 분배(video_builder.py의
# _split_duration_equally())와 수학적으로 동일해진다.
DEFAULT_ROLE_WEIGHT = 1.0

# role별 추천 Ken Burns 모션. 참고용 메타데이터일 뿐, kenburns.py의
# 실제 모션 선택 로직에는 아직 연결되지 않는다.
ROLE_MOTION_HINTS = {
    "environment": "zoom_out",
    "subject": "zoom_in",
    "detail": "static_pan",
    "transition": "pan_horizontal",
}

DEFAULT_MOTION_HINT = "auto"


def plan_asset_usage(assets: list, scene_duration: float) -> list:
    """
    assets(scene["assets"], role 있을 수도/없을 수도 있음)와 scene의
    총 duration을 받아, asset마다 {"path", "role", "duration",
    "motion_hint"}를 순서대로 담은 계획 리스트를 반환합니다. duration
    합은 항상 scene_duration과 정확히 일치합니다. 입력 리스트/dict는
    변경하지 않습니다.
    """

    if not assets:
        return []

    weights = [
        ROLE_DURATION_WEIGHTS.get(asset.get("role"), DEFAULT_ROLE_WEIGHT)
        for asset in assets
    ]
    total_weight = sum(weights)

    plan = []

    for asset, weight in zip(assets, weights):

        role = asset.get("role")

        plan.append({
            "path": asset["path"],
            "role": role,
            "duration": scene_duration * weight / total_weight,
            "motion_hint": ROLE_MOTION_HINTS.get(role, DEFAULT_MOTION_HINT),
        })

    return plan
