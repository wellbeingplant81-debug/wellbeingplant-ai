import json

from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def create_scene_plan(
    topic: str,
    target_duration: int = 45,
):

    prompt = f"""
당신은 유튜브 쇼츠 영상 기획자입니다.

대본을 쓰기 전에, 아래 주제로 만들 영상의 Scene 구조부터 설계하세요.

주제
{topic}

목표 영상 길이
{target_duration}초

규칙

1. scene_count는 주제와 목표 길이에 맞게 직접 결정하세요.
2. 각 scene에는 반드시 아래 항목을 포함하세요.
   - scene_id (1부터 순서대로 매기는 정수)
   - role (예: hook, problem, explanation, evidence, solution, cta 등.
     주제에 맞게 자유롭게 조정 가능)
   - seconds (해당 장면의 길이, 초 단위 정수)
   - goal (이 장면에서 시청자에게 전달하려는 목표)
3. 모든 scene의 seconds 합은 반드시 {target_duration}과 정확히 같아야 합니다.
4. 아직 narration이나 image_prompt는 작성하지 마세요. 오직 구조만 설계합니다.
5. 반드시 아래 JSON 형식으로만 출력하세요.

{{
  "scene_count": 0,
  "scenes": [
    {{
      "scene_id": 1,
      "role": "",
      "seconds": 0,
      "goal": ""
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
        text = (
            text.replace("```json", "")
            .replace("```", "")
            .strip()
        )

    return json.loads(text)
