import os
from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_image(prompt: str):

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=prompt,
    )

    output_dir = "output/images"
    os.makedirs(output_dir, exist_ok=True)

    files = []

    for i, generated_image in enumerate(response.generated_images):

        filename = os.path.join(output_dir, f"scene{i+1}.png")

        generated_image.image.save(filename)

        files.append(filename)

    return {
        "success": True,
        "count": len(files),
        "files": files
    }