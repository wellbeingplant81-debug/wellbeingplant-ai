import json
from google import genai

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

    narration_seconds = max(5, target_duration // scene_count)

    prompt = f"""
당신은 대한민국 최고의 건강 유튜브 쇼츠 기획자이자 영화 감독입니다.

주제
{topic}

다음 조건을 반드시 지켜서 JSON만 출력하세요.

1. title
- 클릭하고 싶은 제목
- 30자 이내

2. hook
- 첫 3초 안에 시청자를 멈추게 하는 문장

3. script
- scenes의 narration을 자연스럽게 이어 붙인 하나의 대본입니다.
- 전체 길이는 약 {target_duration}초 분량입니다.

4. scenes

- 반드시 정확히 {scene_count}개의 scene을 생성하세요.
- scene 번호는 1부터 {scene_count}까지 순서대로 작성하세요.
- 각 narration은 약 {narration_seconds}~{narration_seconds + 2}초 분량으로 작성하세요.
- 모든 scene은 이전 장면과 자연스럽게 이어져야 합니다.

각 scene에는 반드시 아래 항목을 포함하세요.

- scene
- narration
- image_prompt

image_prompt는 반드시 영어로 작성하세요.

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

사람이 등장하면 반드시 포함

- Korean
- realistic skin
- realistic eyes
- realistic hands
- realistic fingers

음식이 등장하면

- Fresh food
- Premium food photography

반드시 아래 JSON 형식으로만 출력하세요.

{{
  "title": "",
  "hook": "",
  "script": "",
  "scenes": [
    {{
      "scene": 1,
      "narration": "",
      "image_prompt": ""
    }}
  ]
}}

위 scene 형식을 반복하여 정확히 {scene_count}개의 scene을 생성하세요.

JSON 외의 다른 설명은 절대 출력하지 마세요.
"""

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
    )

    text = response.text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "").replace("```", "").strip()

    data = json.loads(text)

    return {
        "success": True,
        "data": data,
    }