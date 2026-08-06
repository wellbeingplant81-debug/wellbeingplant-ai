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

Sprint75 - Writer가 문장 하나 대신 요소를 적게 되면서 문제가 하나
생겼다. 요소는 짧게 쓰라고 지시하는데, 인물 일관성은 긴 외형 묘사를
매 Scene 그대로 반복하는 데 달려 있다. 두 지시가 정면으로 싸운다.

실측에서 Writer는 짧은 쪽을 택했다 - "50s Korean man with short neat
black hair with a few grey strands"까지만 적었고 안경과 얼굴 인상이
빠졌다. 텍스트는 Scene마다 똑같았는데도 Gemini는 scene 5, 6의 인물이
다른 사람으로 보인다고 판정했고 character_consistency가 40이 나왔다
(기존 방식 3회는 100/95/95).

그래서 외형 묘사를 Scene에서 빼내 최상위 "character" 한 곳에 둔다.
이미지 생성 단계에서 Reference 슬롯으로 모든 인물 Scene에 붙는다.
Scene의 subject는 짧아도 되고, 앵커는 한 곳에서만 관리된다.

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
그 인물의 외형을 최상위 "character" 필드에 딱 한 번, 자세히 적는다.
영어로 쓴다. 아래를 빠짐없이 포함한다.

- 성별
- 연령대
- 국적/인종
- 머리 모양과 길이와 색
- 안경 착용 여부
- 수염 여부
- 얼굴 인상

예: "a 50s Korean man with short salt-and-pepper hair, thin
rectangular glasses, clean-shaven, warm friendly face, gentle eyes"

이 묘사는 짧게 줄이지 않는다. 짧을수록 매 Scene의 얼굴이 달라진다.

3.
각 Scene의 subject에는 그 인물을 짧게 가리키기만 한다.
예: "the same man", "the same man in sportswear"

외형 묘사를 Scene마다 다시 쓰지 않는다 - 이미지 생성 단계에서
"character" 필드가 모든 인물 Scene에 그대로 붙는다. Scene마다 조금씩
다르게 쓰면 그때부터 얼굴이 갈라진다.

4.
사람이 등장하지 않는 Scene(인체 내부, 음식, 사물, 풍경 등)의
subject에는 인물 묘사를 넣지 않는다. 억지로 사람을 등장시키지 않는다.
손이나 시선처럼 사람을 암시하는 표현도 넣지 않는다.

5.
Scene마다 인물의 옷차림/장소/행동은 내용에 맞게 달라져도 되지만,
얼굴과 머리 모양 등 사람을 식별하는 특징은 절대 바꾸지 않는다.
옷차림과 장소는 action과 environment에 적고, 인물 자체는 subject에
적는다.
"""


def with_character_rules(template_text: str) -> str:
    """
    기존 템플릿 뒤에 인물 일관성 규칙을 덧붙인다. 순수 함수입니다 -
    원본 템플릿 문자열은 그대로 앞에 남는다.
    """

    return f"{template_text}\n{CHARACTER_CONSISTENCY_RULES}\n"
