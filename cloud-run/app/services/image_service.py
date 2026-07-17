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
from app.services.visual_type_classifier import VISUAL_TYPE_AI


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


def generate_image(
    prompt: str,
    output_file: str,
    channel: str = "wellbeing",
    is_thumbnail: bool = False,
    is_hook_scene: bool = False,
    visual_type: str = None,
    aspect_ratio: str = "9:16",
):

    if is_thumbnail:
        style_prompt = THUMBNAIL_STYLE
        negative_prompt = THUMBNAIL_NEGATIVE_PROMPT
    elif visual_type == VISUAL_TYPE_AI:
        # Sprint60 Hotfix - 문제1: 혈관/세포/장내세균 등은 사람 사진이
        # 아니라 의료 일러스트로 생성한다. is_hook_scene이어도(우연히
        # scene 1이 의료 주제인 경우) 이 분기가 우선한다 - hook scene의
        # "강한 임팩트"는 사람 얼굴이 아니라 시각적 대비로 만든다.
        style_prompt = MEDICAL_ILLUSTRATION_STYLE
        negative_prompt = MEDICAL_ILLUSTRATION_NEGATIVE_PROMPT
    elif is_hook_scene:
        base_style = STYLE_MAP.get(
            channel,
            WELLBEING_STYLE,
        )

        style_prompt = base_style + "\n" + HOOK_SCENE_STYLE_BOOST
        negative_prompt = HOOK_SCENE_NEGATIVE_PROMPT
    else:
        style_prompt = STYLE_MAP.get(
            channel,
            WELLBEING_STYLE,
        )

        negative_prompt = NEGATIVE_PROMPT_MAP.get(
            channel,
            WELLBEING_NEGATIVE_PROMPT,
        )

    final_prompt = f"""
{style_prompt}

{prompt}
"""

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=final_prompt,
        config=types.GenerateImagesConfig(
            aspect_ratio=aspect_ratio,
            negative_prompt=negative_prompt,
            add_watermark=False,
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