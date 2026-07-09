"""
Sprint62-5 - Visual Diversity: Sub-prompt Generation.

하나의 image_prompt를 시각적으로 다른 여러 개의 이미지 생성용
서브프롬프트로 분할합니다(동일 장면/인물/상황 유지, 각도·구도·
디테일만 다르게). LLM 호출/응답 파싱이 실패해도 파이프라인이
막히면 안 되므로, 실패 시 항상 image_prompt를 count번 반복한
리스트로 폴백합니다.
"""

import json

from google import genai

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)

SUBPROMPT_COUNT = 4


def generate_subprompts(image_prompt: str, count: int = SUBPROMPT_COUNT) -> list:

    try:
        prompt = f"""
아래 하나의 장면 묘사를 시각적으로 서로 다른 {count}개의 이미지 생성용
프롬프트로 나눠주세요. 같은 장면, 같은 인물, 같은 상황을 유지하되,
카메라 각도/구도/디테일에 초점을 다르게 주어 서로 달라 보이도록
하세요.

장면 묘사
{image_prompt}

반드시 아래 JSON 형식으로만 출력하세요.

{{
  "subprompts": ["...", "...", "...", "..."]
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

        data = json.loads(text)
        subprompts = data["subprompts"]

        if not isinstance(subprompts, list) or len(subprompts) != count:
            raise ValueError(
                f"서브프롬프트 개수가 예상({count})과 다릅니다: {subprompts!r}"
            )

        return subprompts

    except Exception as exc:
        print(
            f"[SubpromptService] 서브프롬프트 생성 실패, image_prompt로 "
            f"폴백: {exc}"
        )
        return [image_prompt] * count
