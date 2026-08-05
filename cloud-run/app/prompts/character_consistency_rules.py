"""
Sprint71 - Character Consistency Engine v1의 Writer 쪽 절반.

측정에서 character_consistency가 5회 전부 0점이었고, 원인은 렌더가
아니라 대본이었다. Writer가 scene 1에 "middle-aged Korean man",
scene 3에 "Korean woman in her 50s", scene 5에 "elderly Korean couple"을
써 놓으면 이미지 파이프라인이 무엇을 하든 같은 사람이 나올 수 없다.

이미지 프롬프트에 "같은 인물"이라고 덧붙이는 방법도 있지만, 그러면
대본이 지정한 인물과 정면으로 어긋난다 - Scene Planner v1이
"close-up shot"에 "wide shot"을 덧붙여 망가뜨렸던 것과 같은 실수다.
인물은 대본이 정하는 것이므로 대본에서 고친다.

지시는 어느 템플릿(SCRIPT_PROMPT / VIRAL_SCRIPT_PROMPT) 뒤에도 그대로
붙일 수 있게 독립된 블록으로 둔다. 두 템플릿을 각각 고치면 한쪽만
바뀌는 일이 생긴다.
"""


CHARACTER_CONSISTENCY_RULES = """
===========================
인물 일관성 규칙
===========================

이 영상에는 주인공이 단 한 명만 등장한다.

1.
사람이 등장하는 Scene에서는 반드시 동일한 한 인물만 등장시킨다.
Scene마다 다른 사람(다른 성별, 다른 연령대, 다른 인물, 부부/커플 등)을
등장시키지 않는다.

2.
그 인물의 외형을 처음 등장할 때 구체적으로 정하고, 이후 모든
image_prompt에서 동일한 표현을 그대로 반복한다. 최소한 아래를
매번 동일하게 적는다.

- 성별
- 연령대
- 국적/인종
- 머리 모양과 길이
- 안경 착용 여부
- 얼굴 인상

예: "the same 50s Korean man with short salt-and-pepper hair,
thin rectangular glasses, clean-shaven, warm friendly face"

3.
사람이 등장하지 않는 Scene(인체 내부, 음식, 사물, 풍경 등)에는
인물 묘사를 넣지 않는다. 억지로 사람을 등장시키지 않는다.

4.
Scene마다 인물의 옷차림/장소/행동은 내용에 맞게 달라져도 되지만,
얼굴과 머리 모양 등 사람을 식별하는 특징은 절대 바꾸지 않는다.
"""


def with_character_rules(template_text: str) -> str:
    """
    기존 템플릿 뒤에 인물 일관성 규칙을 덧붙인다. 순수 함수입니다 -
    원본 템플릿 문자열은 그대로 앞에 남는다.
    """

    return f"{template_text}\n{CHARACTER_CONSISTENCY_RULES}\n"
