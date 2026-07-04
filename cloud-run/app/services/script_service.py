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

    prompt = SCRIPT_PROMPT.substitute(
        topic=topic,
        target_duration=target_duration,
        scene_count=scene_count,
    )

    print("\n" + "=" * 80)
    print("SCRIPT PROMPT")
    print("=" * 80)
    print(prompt)
    print("=" * 80)

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

    print("\n" + "=" * 80)
    print("RAW GEMINI RESPONSE")
    print("=" * 80)
    print(text)
    print("=" * 80)

    data = json.loads(text)

    print("\n" + "=" * 80)
    print("SCENE 1 KEYS")
    print("=" * 80)
    print(data["scenes"][0].keys())
    print("=" * 80)

    return {
        "success": True,
        "data": data,
    }