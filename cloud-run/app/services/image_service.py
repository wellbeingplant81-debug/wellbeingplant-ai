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
    WELLBEING_NEGATIVE_PROMPT,
    FOODBEAT_NEGATIVE_PROMPT,
    MINDTAIL_NEGATIVE_PROMPT,
    THUMBNAIL_NEGATIVE_PROMPT,
    HOOK_SCENE_NEGATIVE_PROMPT,
)


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
):

    if is_thumbnail:
        style_prompt = THUMBNAIL_STYLE
        negative_prompt = THUMBNAIL_NEGATIVE_PROMPT
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
            aspect_ratio="9:16",
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