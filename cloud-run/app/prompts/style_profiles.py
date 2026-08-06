"""
Sprint75 - 채널 스타일을 슬롯으로 분해한 것.

예전 블록(WELLBEING_STYLE 등)은 한 문자열 안에 스타일, 인물 품질, 조명,
카메라, 구도, 부정어가 섞여 있었고 그것이 모든 scene에 통째로 붙었다.
실측한 결과가 이렇다 - 오트밀 그릇 한 장을 그리는 프롬프트가
"Korean people, Natural facial expression, Realistic eyes, Natural skin
pores, ... Correct human anatomy, Realistic hands"로 시작했고, 그
다음이 "85mm portrait photography"였으며, scene이 요구한 "top-down
view of a ceramic bowl"은 그 뒤에 왔다.

분해하면서 세 가지를 옮겼다.

  - 인물 품질 표현은 character 프로필로만 간다. 사물 scene에 사람을
    요구하지 않는다.
  - 카메라는 어느 프로필에도 없다. scene이 정한다.
  - 부정어는 negative 슬롯으로만 간다. 긍정 프롬프트에 "No text"를
    넣지 않는다.

조명은 프로필에 남기되 기본값으로만 쓴다 - scene이 조명을 지정하면
그쪽이 이긴다(prompt_composer.merge).
"""

from app.prompts import prompt_elements as slots
from app.prompts.image_style import (
    FOODBEAT_NEGATIVE_PROMPT,
    MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT,
    MINDTAIL_NEGATIVE_PROMPT,
    THUMBNAIL_NEGATIVE_PROMPT,
    WELLBEING_NEGATIVE_PROMPT,
)


# 인물 사진의 품질을 좌우하는 표현들. 손가락과 피부 질감은 인물이
# 등장할 때만 의미가 있고, 사물 scene에서는 사람을 불러들이는 지시가
# 된다.
_PERSON_QUALITY = [
    "Korean people",
    "natural facial expression",
    "realistic eyes",
    "natural skin pores",
    "healthy skin with natural imperfections",
    "correct human anatomy",
    "realistic hands with correct fingers",
]

_PHOTO_STYLE = [
    "ultra realistic",
    "photorealistic",
    "authentic documentary photography",
    "premium commercial photography",
    "editorial photography",
    "magazine quality",
    "filmic color grading",
    "ultra detailed",
    "extremely sharp focus",
]

# 부정어는 image_style.py 한 곳에서만 정의한다. 두 곳에 두면 한쪽만
# 고쳐지는 날이 온다.
_PHOTO_NEGATIVE = WELLBEING_NEGATIVE_PROMPT

_VERTICAL = "vertical 9:16 framing"


_CHANNEL_STYLE = {
    "wellbeing": _PHOTO_STYLE,
    "foodbeat": [
        "ultra realistic food photography",
        "premium food commercial",
        "luxury food advertisement",
        "restaurant quality",
        "highly detailed texture",
        "fresh water droplets",
        "magazine quality",
        "extremely detailed",
    ],
    "mindtail": [
        "emotional cinematic illustration",
        "Studio Ghibli inspired atmosphere",
        "soft watercolor style",
        "premium animation concept art",
        "beautiful color harmony",
        "highly detailed",
    ],
}

_CHANNEL_LIGHTING = {
    "wellbeing": "soft cinematic lighting, warm natural sunlight, "
                 "high dynamic range",
    "foodbeat": "warm studio lighting, soft reflection, natural shadows",
    "mindtail": "warm sunset lighting",
}

_CHANNEL_COMPOSITION = {
    "wellbeing": "professional composition, beautiful background separation",
    "foodbeat": "professional composition",
    "mindtail": "dreamlike composition",
}

_CHANNEL_NEGATIVE = {
    "wellbeing": WELLBEING_NEGATIVE_PROMPT,
    "foodbeat": FOODBEAT_NEGATIVE_PROMPT,
    "mindtail": MINDTAIL_NEGATIVE_PROMPT,
}


_MEDICAL = {
    slots.STYLE: [
        "medical illustration",
        "scientific visualization",
        "cross-sectional anatomy diagram",
        "microscopic macro photography",
        "biology textbook illustration",
        "scientifically accurate",
        "ultra detailed",
        "extremely sharp focus",
    ],
    slots.LIGHTING: "volumetric lighting, high contrast studio lighting",
    slots.COMPOSITION: "dramatic dark background, vivid saturated colors",
    slots.CONSTRAINTS: _VERTICAL,
    slots.NEGATIVE: MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT,
}

_THUMBNAIL = {
    slots.STYLE: [
        "ultra realistic",
        "photorealistic",
        "professional photography",
        "bright color grading",
        "magazine quality",
        "extremely detailed",
        "extremely sharp focus",
    ],
    slots.LIGHTING: "cinematic lighting, high dynamic range",
    slots.COMPOSITION: "clean composition with a large clear subject",
    slots.CONSTRAINTS: _VERTICAL,
    slots.NEGATIVE: THUMBNAIL_NEGATIVE_PROMPT,
}


# hook scene은 구도와 조명을 더 세게 간다. 카메라는 건드리지 않는다 -
# 그것은 scene이 정한다.
_HOOK_COMPOSITION = (
    "clean simple composition, large clear subject filling the frame, "
    "minimal background clutter, high visual contrast"
)
_HOOK_LIGHTING = "strong dramatic lighting"


def _photo_profile(channel: str, with_person: bool, is_hook_scene: bool):
    style = list(_CHANNEL_STYLE.get(channel, _PHOTO_STYLE))

    if with_person:
        style = style + _PERSON_QUALITY

    return {
        slots.STYLE: style,
        slots.LIGHTING: (
            _HOOK_LIGHTING if is_hook_scene
            else _CHANNEL_LIGHTING.get(channel, _CHANNEL_LIGHTING["wellbeing"])
        ),
        slots.COMPOSITION: (
            _HOOK_COMPOSITION if is_hook_scene
            else _CHANNEL_COMPOSITION.get(
                channel, _CHANNEL_COMPOSITION["wellbeing"],
            )
        ),
        slots.CONSTRAINTS: _VERTICAL,
        slots.NEGATIVE: _CHANNEL_NEGATIVE.get(channel, _PHOTO_NEGATIVE),
    }


def resolve(image_style: str, channel: str, is_hook_scene: bool) -> dict:
    """
    스타일 이름 하나로 슬롯 기본값을 정한다. 순수 함수입니다.

    프로필은 카메라를 절대 채우지 않는다. 카메라는 scene이 정하고,
    두 곳에서 쓰면 서로 싸운다.

    medical은 hook 부스트를 받지 않는다 - 혈관/세포 scene은 hook이어도
    인물 사진 쪽으로 끌려가면 안 된다(Sprint60 실측).
    """

    # 늦은 import - image_service가 이 모듈을 쓰지 않으므로 순환은
    # 없지만, 스타일 이름의 출처를 한 곳으로 유지한다.
    from app.services.image_service import (
        IMAGE_STYLE_CHARACTER, IMAGE_STYLE_DEFAULT, IMAGE_STYLE_MEDICAL,
        IMAGE_STYLE_THUMBNAIL, IMAGE_STYLES,
    )

    if image_style not in IMAGE_STYLES:
        raise ValueError(
            f"알 수 없는 image_style: {image_style!r}. "
            f"사용 가능한 값: {sorted(IMAGE_STYLES)}. "
            f"'real'/'ai'는 provider 라우팅 값이지 스타일이 아닙니다."
        )

    if image_style == IMAGE_STYLE_MEDICAL:
        return dict(_MEDICAL)

    if image_style == IMAGE_STYLE_THUMBNAIL:
        return dict(_THUMBNAIL)

    return _photo_profile(
        channel,
        with_person=(image_style == IMAGE_STYLE_CHARACTER),
        is_hook_scene=is_hook_scene,
    )
