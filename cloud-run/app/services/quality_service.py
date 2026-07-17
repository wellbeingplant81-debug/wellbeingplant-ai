import json
import os

from google import genai
from google.genai import types
from PIL import Image

from app.models.quality_report import AIQualityEvaluation
from app.prompts.quality_rubric import QUALITY_EVALUATION_RUBRIC
from app.services.render_profile import thumbnail_filename


MODEL_NAME = "gemini-2.5-pro"


client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def evaluate(project_path, data, render_profile=None):

    scenes = data["scenes"]

    images = []

    for index in range(1, len(scenes) + 1):

        image_path = os.path.join(project_path, "images", f"scene{index}.png")

        images.append(Image.open(image_path))

    thumbnail_path = os.path.join(project_path, thumbnail_filename(render_profile))

    images.append(Image.open(thumbnail_path))

    script_context = json.dumps(
        {
            "title": data["title"],
            "hook": data["hook"],
            "scenes": [
                {
                    "scene": scene["scene"],
                    "narration": scene["narration"],
                    "image_prompt": scene["image_prompt"],
                }
                for scene in scenes
            ],
        },
        ensure_ascii=False,
    )

    contents = [QUALITY_EVALUATION_RUBRIC, script_context] + images

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AIQualityEvaluation,
        ),
    )

    if response.parsed is None:
        raise ValueError("Gemini did not return a valid structured response")

    return response.parsed
