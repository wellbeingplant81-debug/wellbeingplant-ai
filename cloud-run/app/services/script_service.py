import json

from google import genai
from app.prompts.script_prompt import SCRIPT_PROMPT

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_script(
    topic: str,
    target_duration: int = 45,
    scene_count: int = 6,
):

    prompt = SCRIPT_PROMPT.format(
        topic=topic,
        target_duration=target_duration,
        scene_count=scene_count,
    )

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
    )

    text = response.text.strip()

    if text.startswith("```json"):
        text = (
            text.replace("```json", "")
            .replace("```", "")
            .strip()
        )

    data = json.loads(text)

    return {
        "success": True,
        "data": data,
    }