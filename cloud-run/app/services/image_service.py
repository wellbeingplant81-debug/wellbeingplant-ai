import os

from PIL import (
    Image,
    ImageEnhance,
    ImageFilter,
)

from google import genai

from app.prompts.image_style import (
    WELLBEING_STYLE,
    FOODBEAT_STYLE,
    MINDTAIL_STYLE,
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
):

    style_prompt = STYLE_MAP.get(
        channel,
        WELLBEING_STYLE,
    )

    final_prompt = f"""
{style_prompt}

{prompt}
"""

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=final_prompt,
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