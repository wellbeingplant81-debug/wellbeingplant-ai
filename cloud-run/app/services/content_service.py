from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_short(topic: str):

    prompt = f"""
당신은 대한민국 최고의 건강 유튜브 쇼츠 작가입니다.

주제

{topic}

아래 형식으로 작성하세요.

제목

훅

대본

장면

Scene1
Scene2
Scene3
Scene4

각 Scene마다
- 내레이션
- 이미지 프롬프트

를 작성하세요.
"""

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
    )

    return {
        "success": True,
        "result": response.text
    }