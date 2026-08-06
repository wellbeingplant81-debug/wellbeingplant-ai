"""
Sprint75 - scene의 프롬프트 요소를 다루는 곳.

Writer가 scene마다 문장 하나 대신 요소를 적는다. image_prompt는 그
요소들에서 파생된다 - 스톡 검색과 품질 평가가 계속 그 필드를 읽으므로
없앨 수 없고, 없앨 이유도 없다.

파생된 image_prompt에는 라벨을 붙이지 않는다. 라벨이 붙은 구조는
Imagen에 보내는 프롬프트의 형태이고(prompt_composer), 검색 키워드
추출은 자연스러운 문장을 전제로 한다.
"""

from app.prompts import prompt_elements as slots
from app.services.character_consistency_engine import CHARACTER_SCENE_FIELD


# 인물 앵커를 scene에 실어 두는 필드.
#
# Sprint75 실측 - Reference 슬롯을 만들어 놓고 아무도 채우지 않았다.
# Writer에게 요소를 짧게 쓰라고 지시하면서 동시에 긴 외형 묘사를 매
# Scene 반복하라고 요구했으니, 두 지시가 정면으로 싸웠다. Writer는
# 짧은 쪽을 택했고 텍스트는 Scene마다 동일했는데도
# character_consistency가 40으로 떨어졌다(기존 방식 3회는 100/95/95).
#
# 외형 묘사는 대본 최상위 character 한 곳에 두고 여기로 실어 나른다.
CHARACTER_REFERENCE_FIELD = "character_reference"


# Writer가 scene에 직접 적는 요소들. Reference/Style/Constraints/Negative는
# scene이 아니라 프로필과 대본 전체가 정하므로 여기 없다.
SCENE_ELEMENT_FIELDS = (
    slots.SUBJECT,
    slots.ACTION,
    slots.ENVIRONMENT,
    slots.CAMERA,
    slots.COMPOSITION,
    slots.LIGHTING,
)

# 파생 image_prompt에 넣는 순서. 검색 키워드는 앞쪽에서 뽑히므로
# 피사체가 먼저 온다.
_DERIVED_ORDER = (
    slots.SUBJECT,
    slots.ACTION,
    slots.ENVIRONMENT,
    slots.CAMERA,
    slots.COMPOSITION,
    slots.LIGHTING,
)


def scene_elements(scene: dict, character: str = None) -> dict:
    """
    scene에서 프롬프트 요소만 뽑는다. 순수 함수입니다.

    구버전 대본(문장 하나짜리 image_prompt만 있는 scene)은 빈 dict를
    돌려준다 - 호출자가 그것을 보고 예전 경로로 간다.

    character 앵커는 인물이 등장하는 scene에만 붙인다. 사물 scene에
    인물 묘사를 넣는 것이 정확히 지금까지의 결함이었다.
    """

    elements = {}

    for field in SCENE_ELEMENT_FIELDS:
        value = scene.get(field)

        if value and str(value).strip():
            elements[field] = str(value).strip()

    anchor = character or scene.get(CHARACTER_REFERENCE_FIELD)

    if anchor and scene.get(CHARACTER_SCENE_FIELD):
        elements[slots.REFERENCE] = anchor

    return elements


def attach_character_reference(scenes: list, character: str) -> list:
    """
    인물 앵커를 인물 scene에만 실어 둔다. 입력은 변경하지 않는다.

    integrate_asset은 scene dict 하나만 받는다. 대본 최상위의 character를
    거기까지 전달하려면 scene에 실어 두는 수밖에 없고, 그 편이 병렬
    실행에도 안전하다 - 각 스레드가 자기 scene만 읽는다.

    사물 scene에는 붙이지 않는다. 오트밀 그릇에 인물 묘사를 붙이는 것이
    정확히 Sprint73에서 무너진 자리다.
    """

    if not character or not str(character).strip():
        return [dict(scene) for scene in (scenes or [])]

    anchor = str(character).strip()
    result = []

    for scene in (scenes or []):
        enriched = dict(scene)

        if scene.get(CHARACTER_SCENE_FIELD):
            enriched[CHARACTER_REFERENCE_FIELD] = anchor

        result.append(enriched)

    return result


def derived_image_prompt(elements: dict) -> str:
    """요소들을 검색과 평가가 읽을 한 줄로 잇는다. 순수 함수입니다."""

    return ", ".join(
        elements[slot] for slot in _DERIVED_ORDER if elements.get(slot)
    )


def apply_prompt_elements(scenes: list) -> list:
    """
    요소가 있는 scene의 image_prompt를 채운다. 입력은 변경하지 않는다.

    요소도 없고 image_prompt도 없는 scene은 그대로 둔다. 여기서 조용히
    지어내면 Writer가 실패한 것이 가려진다 - 그 판단은 script_service가
    한다.
    """

    result = []

    for scene in scenes:
        enriched = dict(scene)
        elements = scene_elements(scene)

        if elements:
            enriched["image_prompt"] = derived_image_prompt(elements)

        result.append(enriched)

    return result
