from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)

def test_connection():
    return {"status": "connected"}

def generate_video(prompt: str):
    operation = client.models.generate_videos(
        model="veo-3.1-generate-preview",
        prompt=prompt,
        config=types.GenerateVideosConfig(),
    )

    return {
        "operation": str(operation)
    }