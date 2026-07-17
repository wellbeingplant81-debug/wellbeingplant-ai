import json

from google import genai

from app.prompts.thumbnail_headline_prompt import THUMBNAIL_HEADLINE_PROMPT


client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def generate_thumbnail_headline(topic: str, title: str, hook: str, script: str) -> dict:
    """
    Sprint124 - Thumbnail Headline. title/hook을 그대로 쓰지 않고,
    썸네일 전용으로 2~3줄/10~20자 내외의 강한 호기심 유발 문구를
    별도로 생성한다. 반환값의 keywords는 lines 안에서 빨간색으로
    강조할 단어(1~2개) - 실제 렌더링(빨간색 처리)은 thumbnail_
    service.py의 책임이고, 이 함수는 어떤 단어인지만 결정한다.
    """

    prompt = THUMBNAIL_HEADLINE_PROMPT.substitute(
        topic=topic,
        title=title,
        hook=hook,
        script=script,
    )

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
    elif text.startswith("```"):
        text = text.replace("```", "").strip()

    data = json.loads(text)

    return {
        "lines": data["lines"],
        "keywords": data.get("keywords", []),
    }
