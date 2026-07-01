import json
from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_short(topic: str):

    prompt = f"""
당신은 대한민국 최고의 건강 유튜브 쇼츠 작가입니다.

주제:
{topic}

반드시 아래 JSON 형식으로만 답하세요.
설명은 쓰지 말고 JSON만 출력하세요.

{{
  "title": "...",
  "hook": "...",
  "script": "...",
  "scenes": [
    {{
      "scene": 1,
      "narration": "...",
      "image_prompt": "..."
    }},
    {{
      "scene": 2,
      "narration": "...",
      "image_prompt": "..."
    }},
    {{
      "scene": 3,
      "narration": "...",
      "image_prompt": "..."
    }},
    {{
      "scene": 4,
      "narration": "...",
      "image_prompt": "..."
    }}
  ]
}}
"""

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
    )

    text = response.text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "").replace("```", "").strip()

    return {
        "success": True,
        "data": json.loads(text)
    }