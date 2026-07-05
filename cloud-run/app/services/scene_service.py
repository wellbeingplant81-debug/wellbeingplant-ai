import json
from google import genai

from app.prompts.image_prompt_rules import IMAGE_PROMPT_RULES

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_scenes(script: str):

    prompt = f"""
당신은 영상 감독입니다.

아래 대본을 쇼츠 영상 장면으로 나누세요.

반드시 JSON만 출력하세요.

형식

{{
  "scenes":[
    {{
      "scene":1,
      "duration":"0~5초",
      "narration":"",
      "image_prompt":""
    }}
  ]
}}

image_prompt 작성 시 다음 규칙을 반드시 따르세요.

{IMAGE_PROMPT_RULES}

대본

{script}
"""

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt
    )

    text = response.text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "").replace("```", "").strip()

    return json.loads(text)