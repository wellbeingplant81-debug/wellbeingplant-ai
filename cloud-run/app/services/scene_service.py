import json
from google import genai

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