import os

from PIL import (
    Image,
    ImageEnhance,
    ImageFilter,
)

from google import genai
from google.genai import types

from app.prompts.image_style import (
    WELLBEING_STYLE,
    FOODBEAT_STYLE,
    MINDTAIL_STYLE,
    THUMBNAIL_STYLE,
    HOOK_SCENE_STYLE_BOOST,
    MEDICAL_ILLUSTRATION_STYLE,
    WELLBEING_NEGATIVE_PROMPT,
    FOODBEAT_NEGATIVE_PROMPT,
    MINDTAIL_NEGATIVE_PROMPT,
    THUMBNAIL_NEGATIVE_PROMPT,
    HOOK_SCENE_NEGATIVE_PROMPT,
    MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT,
)

# Sprint71 - 이미지 스타일. provider 라우팅(visual_type: "real"/"ai")과는
# 완전히 다른 축이다.
#
# 예전에는 generate_image()가 visual_type을 읽어 스타일을 정했다. 두
# 개념이 같은 값을 공유하고 있었던 셈인데, Sprint60 시점에는 "ai"가
# 곧 "혈관/세포 주제"였으므로 우연히 맞아떨어졌다. Character
# Consistency가 인물 scene을 Imagen으로 보내면서 그 우연이 깨졌다.
IMAGE_STYLE_DEFAULT = "default"
IMAGE_STYLE_MEDICAL = "medical_illustration"
IMAGE_STYLE_CHARACTER = "character"
IMAGE_STYLE_THUMBNAIL = "thumbnail"

IMAGE_STYLES = frozenset({
    IMAGE_STYLE_DEFAULT,
    IMAGE_STYLE_MEDICAL,
    IMAGE_STYLE_CHARACTER,
    IMAGE_STYLE_THUMBNAIL,
})


client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


STYLE_MAP = {
    "wellbeing": WELLBEING_STYLE,
    "foodbeat": FOODBEAT_STYLE,
    "mindtail": MINDTAIL_STYLE,
}

NEGATIVE_PROMPT_MAP = {
    "wellbeing": WELLBEING_NEGATIVE_PROMPT,
    "foodbeat": FOODBEAT_NEGATIVE_PROMPT,
    "mindtail": MINDTAIL_NEGATIVE_PROMPT,
}


def enhance_image(path: str):

    image = Image.open(path)

    if image.mode != "RGB":
        image = image.convert("RGB")

    image = ImageEnhance.Contrast(
        image
    ).enhance(1.10)

    image = ImageEnhance.Color(
        image
    ).enhance(1.08)

    image = ImageEnhance.Sharpness(
        image
    ).enhance(1.25)

    image = ImageEnhance.Brightness(
        image
    ).enhance(1.02)

    image = image.filter(
        ImageFilter.DETAIL
    )

    image.save(
        path,
        format="PNG",
        optimize=True,
    )


def _resolve_style(image_style: str, channel: str, is_hook_scene: bool):
    """
    스타일 이름 하나로 (style_prompt, negative_prompt)를 정한다.
    순수 함수입니다.

    Sprint71 - 예전에는 이 분기가 visual_type("real"/"ai")을 읽었다.
    그런데 visual_type은 원래 "어느 provider를 먼저 시도할지"를 정하는
    라우팅 값이다. 두 의미가 한 필드에 얹혀 있어서, 인물 scene을
    Imagen으로 보내려고 "ai"를 찍는 순간 스타일까지 의료 일러스트로
    바뀌어 사람 대신 해부학 단면도가 나왔다(실측).

    이제 스타일은 이름으로만 정해진다. 라우팅 어휘가 흘러 들어오면
    조용히 기본값으로 처리하지 않고 즉시 거부한다 - 그래야 다음에
    같은 혼선이 생겼을 때 바로 드러난다.
    """

    if image_style not in IMAGE_STYLES:
        raise ValueError(
            f"알 수 없는 image_style: {image_style!r}. "
            f"사용 가능한 값: {sorted(IMAGE_STYLES)}. "
            f"'real'/'ai'는 provider 라우팅 값이지 스타일이 아닙니다."
        )

    if image_style == IMAGE_STYLE_THUMBNAIL:
        return THUMBNAIL_STYLE, THUMBNAIL_NEGATIVE_PROMPT

    if image_style == IMAGE_STYLE_MEDICAL:
        # Sprint60 Hotfix - 혈관/세포/장내세균 등은 사람 사진이 아니라
        # 의료 일러스트로 생성한다. hook scene이어도 이 분기가 우선한다 -
        # hook의 "강한 임팩트"는 사람 얼굴이 아니라 시각적 대비로 만든다.
        return MEDICAL_ILLUSTRATION_STYLE, MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT

    # IMAGE_STYLE_DEFAULT와 IMAGE_STYLE_CHARACTER는 둘 다 채널 스타일을
    # 쓴다. 인물 scene이라고 해서 다른 화풍을 쓸 이유는 없고, 필요한
    # 것은 "의료 일러스트가 아니어야 한다"는 것뿐이다. 이름을 나눠 둔
    # 이유는 호출자의 의도를 기록으로 남기기 위해서다.
    base_style = STYLE_MAP.get(channel, WELLBEING_STYLE)

    if is_hook_scene:
        return (
            base_style + "\n" + HOOK_SCENE_STYLE_BOOST,
            HOOK_SCENE_NEGATIVE_PROMPT,
        )

    return (
        base_style,
        NEGATIVE_PROMPT_MAP.get(channel, WELLBEING_NEGATIVE_PROMPT),
    )


def _build_prompt(prompt: str, image_style: str, channel: str,
                  is_hook_scene: bool):
    style_prompt, negative_prompt = _resolve_style(
        image_style, channel, is_hook_scene,
    )

    return (
        f"""
{style_prompt}

{prompt}
""",
        negative_prompt,
    )


def _write_generated(generated, output_file: str) -> str:
    """생성된 이미지 한 장을 파일로 쓴다."""

    if generated.image is None:
        raise Exception(
            "Image 객체가 없습니다."
        )

    if generated.image.image_bytes is None:
        raise Exception(
            "image_bytes가 없습니다."
        )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as f:
        f.write(generated.image.image_bytes)

    enhance_image(output_file)

    print(f"Saved : {output_file}")

    return output_file


def generate_image_candidates(
    prompt: str,
    output_files: list,
    channel: str = "wellbeing",
    is_hook_scene: bool = False,
    image_style: str = IMAGE_STYLE_DEFAULT,
):
    """
    Sprint74 - 같은 프롬프트로 후보를 여러 장 받는다.

    Imagen은 한 요청에 여러 장을 돌려준다. generate_image를 N번 부르면
    왕복도 N번이지만, 이쪽은 한 번이다.

    요청한 것보다 적게 돌아올 수 있다(안전 필터 등). 그것은 오류가
    아니라 후보가 줄어든 것이므로, 받은 만큼만 쓰고 그만큼의 경로를
    돌려준다. 한 장도 못 받은 경우만 예외다.
    """

    final_prompt, negative_prompt = _build_prompt(
        prompt, image_style, channel, is_hook_scene,
    )

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=final_prompt,
        config=types.GenerateImagesConfig(
            aspect_ratio="9:16",
            negative_prompt=negative_prompt,
            add_watermark=False,
            number_of_images=len(output_files),
        ),
    )

    if not response.generated_images:
        raise Exception(
            "Imagen이 이미지를 생성하지 않았습니다."
        )

    return [
        _write_generated(generated, output_file)
        for generated, output_file in zip(
            response.generated_images, output_files,
        )
    ]


def generate_image(
    prompt: str,
    output_file: str,
    channel: str = "wellbeing",
    is_hook_scene: bool = False,
    image_style: str = IMAGE_STYLE_DEFAULT,
):

    style_prompt, negative_prompt = _resolve_style(
        image_style, channel, is_hook_scene,
    )

    final_prompt = f"""
{style_prompt}

{prompt}
"""

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=final_prompt,
        config=types.GenerateImagesConfig(
            aspect_ratio="9:16",
            negative_prompt=negative_prompt,
            add_watermark=False,
            # Sprint74 - 이 줄이 없던 동안 Vertex는 자기 기본값인 4장을
            # 만들었고, 아래에서 [0]만 저장했다. 나머지 세 장은 요금이
            # 청구된 뒤 그대로 버려졌다.
            #
            # 여러 장이 필요하면 generate_image_candidates를 쓴다.
            # 이 함수는 한 장을 쓰므로 한 장만 요청한다.
            number_of_images=1,
        ),
    )

    if not response.generated_images:
        raise Exception(
            "Imagen이 이미지를 생성하지 않았습니다."
        )

    generated = response.generated_images[0]

    if generated.image is None:
        raise Exception(
            "Image 객체가 없습니다."
        )

    if generated.image.image_bytes is None:
        raise Exception(
            "image_bytes가 없습니다."
        )

    os.makedirs(
        os.path.dirname(output_file),
        exist_ok=True,
    )

    with open(
        output_file,
        "wb",
    ) as f:

        f.write(
            generated.image.image_bytes
        )

    enhance_image(
        output_file
    )

    print(
        f"Saved : {output_file}"
    )

    return output_file