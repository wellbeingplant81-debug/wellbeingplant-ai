"""
Sprint72-1 - Visual Diversity Engine.

Sprint70(Ken Burns Motion Diversity)/Sprint71(Hybrid Asset Composer)에
이어, 생성되는 AI 이미지 자체의 구도/카메라 연출을 scene마다 다르게
가져가 "AI가 만든 비슷한 그림" 느낌을 줄인다. Sprint62-3의 subprompt_
service.py(같은 scene 안 4개 asset끼리의 다양성, LLM이 SHOT_TYPES 등을
직접 판단)와는 다른 축이다 - 이 모듈은 scene 하나에 대해 결정적으로
Camera Distance/Angle/Composition/Lighting 조합 하나("Profile")를
고르고, image_prompt에 텍스트로 얹어 그 scene의 모든 AI 이미지(1차 +
extra)가 같은 Profile을 공유하게 만든다. AI 호출 없이 순수 함수로만
동작한다.
"""

CAMERA_DISTANCES = ["wide", "medium", "close-up", "macro"]

CAMERA_ANGLES = [
    "eye level", "low angle", "high angle",
    "top-down", "side view", "over shoulder",
]

COMPOSITIONS = ["centered", "rule of thirds", "foreground framing", "leading lines"]

LIGHTING_STYLES = [
    "soft daylight", "dramatic light", "warm indoor", "cool ambient", "backlit",
]


def assign_visual_profiles(scenes: list) -> dict:
    """
    scene 목록을 받아 {scene_number: profile} 딕셔너리를 반환합니다.
    각 차원(camera_distance/camera_angle/composition/lighting)은
    scene 순서에 따라 독립적으로 순환(round-robin)합니다 - 차원마다
    리스트 길이가 다르므로(4/6/4/5) 같은 인덱스라도 네 차원이 동시에
    겹치는 조합이 자연스럽게 잘 나오지 않습니다.

    요구사항3(동일 영상에서 같은 Camera Angle/Distance 조합 반복 금지)을
    위해 (camera_distance, camera_angle) 조합이 이미 배정됐으면 다음
    camera_angle 후보로 넘어가 충돌을 피합니다 - scene 개수가
    len(CAMERA_DISTANCES)*len(CAMERA_ANGLES)(=24) 이내인 한 항상
    가능합니다. 순수 함수입니다 - 입력 scenes를 변경하지 않습니다.
    """

    if not scenes:
        return {}

    profiles = {}
    used_combos = set()

    for index, scene in enumerate(scenes):

        distance = CAMERA_DISTANCES[index % len(CAMERA_DISTANCES)]
        angle = CAMERA_ANGLES[index % len(CAMERA_ANGLES)]

        offset = 0
        while (distance, angle) in used_combos and offset < len(CAMERA_ANGLES):
            offset += 1
            angle = CAMERA_ANGLES[(index + offset) % len(CAMERA_ANGLES)]

        used_combos.add((distance, angle))

        profiles[scene["scene"]] = {
            "camera_distance": distance,
            "camera_angle": angle,
            "composition": COMPOSITIONS[index % len(COMPOSITIONS)],
            "lighting": LIGHTING_STYLES[index % len(LIGHTING_STYLES)],
        }

    return profiles


def profile_to_text(profile: dict) -> str:
    """Profile을 image_prompt에 이어 붙일 수 있는 하나의 문구로 합칩니다."""

    return (
        f"{profile['camera_distance']} shot, {profile['camera_angle']}, "
        f"{profile['composition']} composition, {profile['lighting']}"
    )


def apply_profile_to_prompt(image_prompt: str, profile: dict) -> str:
    """
    기존 image_prompt 끝에 Profile 문구를 덧붙입니다. prompt_styler.
    apply_style_to_prompt()와 동일한 계약입니다 - profile이 없으면
    (visual_profile=None, 기본값) 원본을 그대로 반환해 완전히 하위
    호환됩니다. 이미 같은 문구가 있으면 중복으로 다시 덧붙이지
    않습니다(재실행/재생성 대비).
    """

    if not image_prompt or not profile:
        return image_prompt

    profile_text = profile_to_text(profile)

    if profile_text in image_prompt:
        return image_prompt

    return f"{image_prompt} {profile_text}."
