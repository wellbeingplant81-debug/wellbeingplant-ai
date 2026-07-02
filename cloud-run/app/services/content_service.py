import json
from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_short(topic: str):

    prompt = f"""
당신은 대한민국 최고의 건강 유튜브 쇼츠 기획자이자 영화 감독입니다.

주제
{topic}

다음 조건을 반드시 지켜서 JSON만 출력하세요.

1. title
- 클릭하고 싶은 제목
- 30자 이내

2. hook
- 첫 3초 시청자를 멈추게 하는 문장

3. script
- 약 40~60초 분량
- 자연스럽게 이어지는 하나의 대본

4. scenes
- 총 4개의 장면
- scene 번호는 1~4

각 scene에는 아래 항목을 작성하세요.

- narration
  해당 장면에서 읽는 나레이션

- image_prompt
  반드시 영어로 작성

image_prompt 작성 규칙

- Ultra realistic
- Cinematic photography
- Documentary style
- Professional photography
- Korean people
- Natural facial expression
- Correct human anatomy
- Warm natural lighting
- Highly detailed
- Photorealistic
- 8K quality
- Shallow depth of field
- Vertical composition 9:16
- No text
- No watermark
- No logo
- No illustration
- No cartoon
- No CGI

사람이 등장하면

- Korean
- realistic skin
- realistic eyes
- realistic hands
- realistic fingers

를 반드시 포함하세요.

음식이 등장하면

매우 신선하고
광고 사진 수준의 퀄리티로 표현하세요.

JSON 형식은 반드시 아래처럼 출력하세요.

{{
  "title": "",
  "hook": "",
  "script": "",
  "scenes": [
    {{
      "scene": 1,
      "narration": "",
      "image_prompt": ""
    }},
    {{
      "scene": 2,
      "narration": "",
      "image_prompt": ""
    }},
    {{
      "scene": 3,
      "narration": "",
      "image_prompt": ""
    }},
    {{
      "scene": 4,
      "narration": "",
      "image_prompt": ""
    }}
  ]
}}

JSON 외의 다른 설명은 절대 출력하지 마세요.
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