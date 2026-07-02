import json

from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_topics(category: str, count: int):

    prompt = f"""
당신은 대한민국 최고의 건강 유튜브 기획자입니다.

카테고리:
{category}

조회수가 잘 나올 건강 쇼츠 주제를 {count}개 만들어주세요.

조건

- 40~60대가 클릭하고 싶은 제목
- 실제 의학적으로 말이 되는 내용
- 너무 흔한 주제 제외
- 호기심을 자극
- JSON만 출력

형식

{{
    "topics":[
        "...",
        "...",
        "..."
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

    return json.loads(text)