from app.services.style_profile_builder import style_profile_to_text


def apply_style_to_prompt(image_prompt: str, profile: dict) -> str:
    """
    기존 image_prompt 끝에 스타일 프로필 문구를 덧붙입니다. 순수
    함수이며 narration 등 다른 필드는 건드리지 않고, image_prompt의
    내용 자체도 지우거나 바꾸지 않습니다(끝에 덧붙이기만 함).

    이미 동일한 스타일 문구가 포함되어 있으면 중복으로 다시
    덧붙이지 않습니다 - 파이프라인 재실행/재생성 시 같은 문구가
    계속 누적되는 것을 방지합니다.
    """

    if not image_prompt:
        return image_prompt

    style_text = style_profile_to_text(profile)

    if style_text in image_prompt:
        return image_prompt

    return f"{image_prompt} {style_text}."


def annotate_scenes_with_style(scenes: list, profile: dict) -> list:
    """
    scene 목록의 image_prompt에 동일한 스타일 프로필을 일괄
    적용한 새 리스트를 반환합니다. 입력 scenes는 변경하지 않고,
    scene 순서도 바꾸지 않습니다.
    """

    return [
        {
            **scene,
            "image_prompt": apply_style_to_prompt(
                scene.get("image_prompt", ""), profile,
            ),
        }
        for scene in scenes
    ]
