HOOK_TRANSITION = "fade"
NORMAL_TRANSITION = "cross_dissolve"

# 이번 스프린트의 배정 규칙(hook=강한 전환, 나머지=일반 전환)에서는
# 사용되지 않지만, transition_engine이 지원해야 하는 효과 목록에
# 포함되어 있어 상수로만 남겨둡니다 - 향후 규칙 확장 시 사용.
SMOOTH_CUT = "smooth_cut"

SUPPORTED_TRANSITIONS = (HOOK_TRANSITION, NORMAL_TRANSITION, SMOOTH_CUT)


def assign_transition(scene_number: int) -> str:
    """
    scene 번호에 따라 transition 타입을 결정합니다. 순수 함수입니다.

    규칙: hook scene(1번)은 강한 전환(fade), 그 외 scene은 일반
    전환(cross_dissolve)을 사용합니다.
    """

    return HOOK_TRANSITION if scene_number == 1 else NORMAL_TRANSITION


def annotate_scenes_with_transitions(scenes: list) -> list:
    """
    각 scene에 transition 필드를 추가한 새 scene 리스트를 반환합니다.
    입력 scene들은 변경하지 않습니다.

    주의: 이 필드는 결정/기록용 메타데이터입니다. 실제 Ken
    Burns/비디오 렌더링(video_builder.py, kenburns.py)에는 아직
    반영되지 않습니다 - "video_builder 구조 변경 최소화" 원칙에 따라
    이번 스프린트는 여기까지만 다룹니다.
    """

    return [
        {**scene, "transition": assign_transition(scene["scene"])}
        for scene in scenes
    ]
