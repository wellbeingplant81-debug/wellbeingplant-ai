from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_script(topic: str):

    prompt = f"""
당신은 40~60대를 위한 건강 유튜브 쇼츠 전문 작가입니다.

주제:
{topic}

형식

1. 강력한 훅
2. 이유 설명
3. 위험 신호
4. 병원 어디 가야 하는지
5. CTA

자연스럽고 짧게 작성하세요.
"""

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt
    )

    return {
        "script": response.text
    }