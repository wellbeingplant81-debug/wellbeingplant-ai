from app.services.color_mood_engine import build_color_mood

MINIMAL_COMPOSITION = "minimal composition"
CINEMATIC_FEEL = "cinematic feel"

DEFAULT_CHANNEL = "wellbeing"


def build_style_profile(channel: str = DEFAULT_CHANNEL) -> dict:
    """
    영상 하나에 적용할 스타일 프로필을 생성합니다. 순수 함수입니다.

    현재는 channel과 무관하게 고정된 웰빙 브랜드 기준(warm/soft/
    clean/wellness aesthetic, natural morning lighting, minimal
    composition, cinematic feel)을 반환합니다 - channel 인자는 향후
    채널/주제별로 프로필이 달라질 수 있도록 남겨둔 확장 지점입니다.
    """

    return {
        "channel": channel,
        "color_mood": build_color_mood(),
        "composition": MINIMAL_COMPOSITION,
        "cinematic": CINEMATIC_FEEL,
    }


def style_profile_to_text(profile: dict) -> str:
    """
    스타일 프로필을 image_prompt에 이어 붙일 수 있는 하나의 문구로
    합칩니다. 순수 함수입니다.
    """

    return ", ".join(
        [
            profile["color_mood"],
            profile["composition"],
            profile["cinematic"],
        ]
    )
