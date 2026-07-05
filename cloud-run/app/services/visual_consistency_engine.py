from app.services.prompt_styler import annotate_scenes_with_style
from app.services.style_profile_builder import build_style_profile, DEFAULT_CHANNEL


def apply_visual_consistency(scenes: list, channel: str = DEFAULT_CHANNEL) -> list:
    """
    Sprint34 - Visual Consistency Engine 진입점.

    영상 하나에 대해 스타일 프로필을 한 번 만들고, 모든 scene의
    image_prompt에 동일하게 적용해 scene끼리 스타일/톤/분위기가
    통일되도록 합니다.

    asset 선택(get_candidates/select_best)이나 scoring 로직에는
    전혀 관여하지 않고 image_prompt 텍스트만 바꿉니다. 입력 scenes는
    변경하지 않습니다.
    """

    profile = build_style_profile(channel)

    return annotate_scenes_with_style(scenes, profile)
