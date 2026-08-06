import json

from google import genai

from app import config
from app.prompts.character_consistency_rules import with_character_rules
from app.prompts.script_prompt import SCRIPT_PROMPT
from app.prompts.viral_script_prompt import VIRAL_SCRIPT_PROMPT
from app.services import scene_prompt_service


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

    template = VIRAL_SCRIPT_PROMPT if config.ENABLE_VIRAL_WRITER else SCRIPT_PROMPT

    prompt = template.substitute(
        topic=topic,
        target_duration=target_duration,
        scene_count=scene_count,
    )

    # Sprint71 - Character Consistency v1. 인물 일관성은 대본이 정하는
    # 것이므로 여기서 규칙을 얹는다. 두 템플릿 중 무엇이 선택됐든
    # 동일하게 붙으므로, 한쪽만 반영되는 일이 없다.
    if config.ENABLE_CHARACTER_CONSISTENCY:
        prompt = with_character_rules(prompt)

    print("\n" + "=" * 80)
    print("SCRIPT PROMPT")
    print("=" * 80)
    print(prompt)
    print("=" * 80)

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

    print("\n" + "=" * 80)
    print("RAW GEMINI RESPONSE")
    print("=" * 80)
    print(text)
    print("=" * 80)

    data = json.loads(text)

    # Sprint75 - Writer는 이제 scene마다 요소(subject/action/environment/
    # camera/composition/lighting)를 적는다. image_prompt는 거기서
    # 파생된다 - 스톡 검색과 품질 평가가 계속 그 필드를 읽는다.
    #
    # 구버전 대본(문장 하나짜리 image_prompt)이 들어와도 그대로 통과한다.
    data["scenes"] = scene_prompt_service.apply_prompt_elements(
        data["scenes"],
    )

    print("\n" + "=" * 80)
    print("SCENE 1 KEYS")
    print("=" * 80)
    print(data["scenes"][0].keys())
    print("=" * 80)

    return {
        "success": True,
        "data": data,
    }