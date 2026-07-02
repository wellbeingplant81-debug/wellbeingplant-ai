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

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    image = response.generated_images[0]

    image.image.save(output_file)

    return output_file