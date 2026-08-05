"""
Sprint71 - Character Consistency Engine v1의 이미지 쪽 절반.

Writer가 한 인물만 등장시키도록 고쳐도(app/prompts/
character_consistency_rules.py), 그 인물이 화면에 그대로 나오는 것은
아니다. 실측한 영상은 인물이 나오는 6개 scene 중 4개를 Pexels 스톡에서
가져왔는데, 스톡은 매번 다른 실제 사람 사진이다. 대본이 "같은 50대
한국 남성"이라고 아무리 적어도 스톡 검색은 그 사람을 찾아 줄 수 없다.

그래서 이 모듈이 하는 일은 하나다 - 인물이 등장하는 scene을 Imagen
경로로 보낸다. 그것뿐이다.

특히 image_prompt는 한 글자도 건드리지 않는다. 여기서 "같은 인물"
같은 문구를 덧붙이면 대본이 이미 적어 둔 인물 묘사와 어긋난다.
Scene Planner v1이 "close-up shot"으로 시작하는 프롬프트에 "wide shot"을
덧붙여 이미지를 망가뜨렸던 것과 정확히 같은 실수가 된다. 프롬프트를
쓰는 것은 Writer의 일이고, 이 모듈의 일은 경로를 정하는 것이다.
"""

import re

from app.services.visual_type_classifier import VISUAL_TYPE_AI


# 인물 scene임을 표시하는 필드.
#
# visual_type만으로는 안 된다. image_service에서 visual_type == "ai"는
# "Imagen으로 생성"이 아니라 "의료 일러스트 스타일로 생성"을 뜻한다
# (Sprint60 Hotfix). 인물 scene에 "ai"만 찍어 두면 사람 대신 해부학
# 단면도가 나온다 - 실측으로 확인했다.
#
# 그래서 두 의미를 갈라 놓는다. 라우팅(Imagen 우선)은 visual_type이,
# 스타일(의료 일러스트냐 인물이냐)은 이 필드가 정한다.
CHARACTER_SCENE_FIELD = "character_scene"


# 화면에 사람이 있다는 신호. narration이 아니라 image_prompt만 본다 -
# "많은 사람들이 이 습관을 놓칩니다" 같은 나레이션은 화면에 사람이
# 없어도 얼마든지 나온다.
PERSON_KEYWORDS = {
    "man", "men", "woman", "women", "person", "people", "couple",
    "boy", "girl", "male", "female", "lady", "gentleman",
    "patient", "doctor", "physician", "nurse", "family",
    "adult", "adults", "senior", "seniors", "elderly",
    "남성", "여성", "남자", "여자", "사람", "인물", "부부", "커플",
    "환자", "의사", "간호사", "노인", "어르신", "아이", "가족",
}

# 사람의 일부만 나오는 장면도 인물 장면이다 - 손 하나가 나와도 다음
# scene의 손과 같은 사람이어야 하고, 스톡에서는 그것이 보장되지 않는다.
BODY_PART_KEYWORDS = {
    "hand", "hands", "face", "shoulder", "arm", "arms", "leg", "legs",
    "foot", "feet", "손", "얼굴", "어깨", "팔", "다리", "발",
}

# "human artery", "human body" 처럼 인체 구조를 가리키는 표현은 인물이
# 아니다. 이걸 걸러내지 않으면 혈관/세포 장면이 전부 인물 경로로
# 새어 들어간다.
ANATOMY_CONTEXT = re.compile(
    r"\bhuman\s+(?:artery|arteries|vein|veins|body|cell|cells|organ|"
    r"organs|heart|brain|tissue|blood|anatomy)\b"
)


def _matches(keyword: str, text: str) -> bool:
    """
    ASCII 키워드는 단어 경계로 정확히 매칭하고(부분 문자열 오탐 방지),
    한글 키워드는 조사가 붙는 특성상 포함으로 매칭한다 -
    visual_type_classifier._matches()와 같은 방식이다.
    """

    if keyword.isascii():
        return bool(re.search(r"\b" + re.escape(keyword) + r"\b", text))

    return keyword in text


def features_person(scene: dict) -> bool:
    """
    이 scene의 화면에 사람이 등장하는지 판정한다. 순수 함수입니다.

    image_prompt만 본다 - 라우팅을 정하는 근거는 화면이지 나레이션이
    아니다.
    """

    prompt = (scene or {}).get("image_prompt") or ""

    if not prompt:
        return False

    text = prompt.lower()

    # 인체 구조 표현을 먼저 지운다. "human artery"의 human이 인물로
    # 읽히면 안 된다.
    text = ANATOMY_CONTEXT.sub(" ", text)

    for keyword in PERSON_KEYWORDS | BODY_PART_KEYWORDS:
        if _matches(keyword.lower(), text):
            return True

    return False


def character_scene_numbers(scenes: list) -> list:
    """인물이 등장하는 scene 번호를 순서대로 돌려준다."""

    return [
        scene["scene"]
        for scene in (scenes or [])
        if features_person(scene)
    ]


def apply_character_routing(scenes: list) -> list:
    """
    인물이 등장하는 scene의 visual_type을 "ai"로 바꾼 새 리스트를
    돌려준다. 그 외에는 아무것도 바꾸지 않는다 - image_prompt,
    narration, scene 순서 전부 그대로다. 입력 scenes는 변경하지
    않습니다.

    사람이 없는 scene의 routing은 손대지 않는다. 혈관 macro나 신발
    클로즈업은 인물 일관성과 무관하고, 이미 visual_type_classifier가
    정해 둔 판단이 있다.
    """

    routed = []

    for scene in (scenes or []):

        new_scene = dict(scene)

        if features_person(scene):
            new_scene["visual_type"] = VISUAL_TYPE_AI
            new_scene[CHARACTER_SCENE_FIELD] = True

        routed.append(new_scene)

    return routed
