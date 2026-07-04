import os
from pprint import pformat

from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


import os

from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_image(prompt: str, output_file: str):

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=prompt,
    )

    if not response.generated_images:
        raise Exception("Imagen이 이미지를 생성하지 않았습니다.")

    generated = response.generated_images[0]

    if generated.image is None:
        raise Exception("Image 객체가 없습니다.")

    if generated.image.image_bytes is None:
        raise Exception("image_bytes가 없습니다.")

    os.makedirs(
        os.path.dirname(output_file),
        exist_ok=True,
    )

    with open(output_file, "wb") as f:
        f.write(generated.image.image_bytes)

    print(f"Saved : {output_file}")

    return output_file