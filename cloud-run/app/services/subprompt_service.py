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

# Sprint63-1 - Visual Diversity 품질 향상. count가 기본값(4)과 같으면
# 이 순서대로 서로 다른 화면 구성(shot type)을 하나씩 명시적으로
# 요청해 중복 프롬프트를 줄인다.
SHOT_TYPES = ["wide shot", "medium shot", "close-up", "detail shot"]

# Sprint63-2 - Shot Type뿐 아니라 의미적 초점(focus)도 SHOT_TYPES와
# 1:1로 짝지어 함께 요청한다 - "화면만 다르고 의미는 같은" 서브프롬프트
# (예: 4개 전부 인물 클로즈업 계열)를 방지한다.
FOCUS_TYPES = ["environment", "subject", "action", "supporting object"]

# Sprint63-3 - Visual Composition 다양성 강화. 위 SHOT_TYPES/FOCUS_TYPES
# 와 동일하게 1:1로 짝지어, camera angle/composition/subject distance
# 까지 서로 겹치지 않도록 함께 요청한다.
CAMERA_ANGLES = ["eye level", "low angle", "high angle", "over-the-shoulder"]
COMPOSITIONS = ["centered", "rule of thirds", "foreground emphasis", "background emphasis"]
SUBJECT_DISTANCES = ["full body", "half body", "close detail", "wide environment"]


def _shot_type_instruction(count: int) -> str:

    if count != len(SHOT_TYPES):
        return (
            f"{count}개 모두 촬영 거리/구도/주목 대상이 서로 뚜렷하게 "
            f"다른 화면 구성을 사용하세요."
        )

    numbered = "\n".join(
        f"{i + 1}. {shot_type} - {focus_type} 중심 / camera angle: "
        f"{camera_angle} / composition: {composition} / subject "
        f"distance: {distance} (shot {i + 1})"
        for i, (shot_type, focus_type, camera_angle, composition, distance)
        in enumerate(
            zip(SHOT_TYPES, FOCUS_TYPES, CAMERA_ANGLES, COMPOSITIONS, SUBJECT_DISTANCES)
        )
    )

    return (
        "각 서브프롬프트는 아래 순서의 화면 구성(shot type), 의미적 "
        "초점(focus), camera angle, composition, subject distance를 "
        "정확히 하나씩 함께 사용하세요 - 화면, 의미, 카메라 앵글, 구도, "
        f"피사체와의 거리 중 어느 하나도 겹치면 안 됩니다.\n{numbered}"
    )


def _has_duplicate_subprompts(subprompts: list) -> bool:

    normalized = [
        " ".join(subprompt.strip().lower().split())
        for subprompt in subprompts
    ]

    return len(set(normalized)) != len(normalized)


def generate_subprompts(image_prompt: str, count: int = SUBPROMPT_COUNT) -> list:

    try:
        prompt = f"""
아래 하나의 장면 묘사를 시각적으로 서로 다른 {count}개의 이미지 생성용
프롬프트로 나눠주세요. 같은 장면, 같은 인물, 같은 상황을 유지하되,
서로 다른 화면이 나오도록 하세요.

{_shot_type_instruction(count)}

절대로 같은 문장을 반복하거나 서로 거의 동일한 프롬프트를 만들지
마세요 - 중복 없이 반드시 서로 뚜렷하게 구별되어야 합니다. 문장
표현뿐 아니라 의미(무엇을 보여주는지)도 겹치지 않아야 합니다.

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

        if _has_duplicate_subprompts(subprompts):
            raise ValueError(
                f"서브프롬프트에 중복이 있습니다: {subprompts!r}"
            )

        return subprompts

    except Exception as exc:
        print(
            f"[SubpromptService] 서브프롬프트 생성 실패, image_prompt로 "
            f"폴백: {exc}"
        )
        return [image_prompt] * count
