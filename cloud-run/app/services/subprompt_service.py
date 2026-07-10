"""
Sprint62-5 - Visual Diversity: Sub-prompt Generation.

하나의 image_prompt를 시각적으로 다른 여러 개의 이미지 생성용
서브프롬프트로 분할합니다(동일 장면/인물/상황 유지, 각도·구도·
디테일만 다르게). LLM 호출/응답 파싱이 실패해도 파이프라인이
막히면 안 되므로, 실패 시 항상 image_prompt를 count번 반복한
리스트로 폴백합니다.
"""

import json
import re

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


# Sprint63-4 - Quality Gate: 두 서브프롬프트의 단어 집합 Jaccard
# 유사도가 이 값 이상이면 "표현만 다를 뿐 사실상 같은 키워드 반복"으로
# 보고 폴백한다.
KEYWORD_OVERLAP_THRESHOLD = 0.8

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set:
    return set(_WORD_RE.findall(text.lower()))


def _has_near_duplicate_keywords(subprompts: list) -> bool:

    token_sets = [_tokenize(subprompt) for subprompt in subprompts]

    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            union = token_sets[i] | token_sets[j]
            if not union:
                continue
            overlap = len(token_sets[i] & token_sets[j]) / len(union)
            if overlap >= KEYWORD_OVERLAP_THRESHOLD:
                return True

    return False


# Sprint66-1 - Quality Gate 언어 불일치 수정. Sprint65 실제 E2E에서
# Gemini가 focus/camera angle/composition/subject distance는 한국어+
# 영어 괄호 병기로 응답하면서 shot type만 한글 음차로만 응답해(예:
# "와이드 샷"), 영어 리터럴만 찾는 _has_missing_dimension()이 정상
# 응답을 "축 전체 누락"으로 오판하는 문제가 있었다. 프롬프트 생성
# 지시문(SHOT_TYPES 등)은 그대로 두고, 검증 시에만 각 영어 키워드의
# 한국어/자연어 alias를 함께 인정한다.
DIMENSION_ALIASES = {
    "wide shot": ["와이드 샷", "와이드샷"],
    "medium shot": ["미디엄 샷", "미디엄샷"],
    "close-up": ["클로즈업"],
    "detail shot": ["디테일 샷", "디테일샷"],
    "environment": ["환경"],
    "subject": ["피사체", "대상", "인물"],
    "action": ["행동", "행위"],
    "supporting object": ["소품", "보조 사물"],
    "eye level": ["아이레벨", "아이 레벨", "눈높이"],
    "low angle": ["로우앵글", "로우 앵글", "낮은 앵글"],
    "high angle": ["하이앵글", "하이 앵글", "높은 앵글"],
    "over-the-shoulder": ["오버 더 숄더", "어깨 너머"],
    "centered": ["중앙 구도", "화면 중앙", "센터드", "center"],
    "rule of thirds": ["삼분할", "3분할", "third of the frame"],
    # Sprint67-2 - "foreground"/"background"와 "emphasis"(자연어에서는
    # "emphasizes"/"emphasized"처럼 다른 문장에 떨어져 나오기도 함,
    # 실제 로그 확인)가 함께 등장하는지를 별도로 인정한다. 튜플은
    # "이 단어들이 전부(어순 무관) combined_text 어딘가에 있어야
    # 한다"는 의미 - "foreground"만 있고 emphasis 언급이 전혀 없는
    # 경우까지 통과시키는 과도하게 느슨한 매칭은 아니다.
    "foreground emphasis": ["전경 강조", "전경을 강조", ("foreground", "emphas")],
    "background emphasis": ["배경 강조", "배경을 강조", ("background", "emphas")],
    "full body": ["전신"],
    "half body": ["상반신", "허리까지"],
    "close detail": ["근접 디테일", "가까운 디테일"],
    "wide environment": ["넓은 환경", "넓은 배경"],
}


def _normalize_for_matching(text: str) -> str:
    # Sprint67-2 - "eye-level"/"low-angle"/"high-angle"처럼 canonical
    # 표현(공백)을 하이픈으로 바꿔 쓰는 자연어 변형을 흡수한다.
    return text.replace("-", " ")


def _mentions_keyword(combined_text: str, keyword: str) -> bool:

    normalized_text = _normalize_for_matching(combined_text)

    if _normalize_for_matching(keyword) in normalized_text:
        return True

    for alias in DIMENSION_ALIASES.get(keyword, []):

        if isinstance(alias, tuple):
            if all(word in normalized_text for word in alias):
                return True
        elif _normalize_for_matching(alias) in normalized_text:
            return True

    return False


def _has_missing_dimension(subprompts: list) -> bool:
    """
    Sprint63-4 - Shot Type/Focus Type/Camera Angle/Composition/Subject
    Distance 중 어느 하나라도 4개의 서브프롬프트 전체를 통틀어 단 한
    번도 언급되지 않았으면(LLM이 해당 축 지시를 완전히 무시함) True를
    반환한다. 항목별 1:1 배치까지는 강제하지 않는다 - 자연어 응답의
    표현 편차를 허용하면서도, 축 전체가 통째로 누락된 명백한 실패만
    잡아낸다. Sprint66-1 - 영어 키워드뿐 아니라 DIMENSION_ALIASES의
    한국어/자연어 표현도 함께 인정한다.
    """

    combined_text = " ".join(subprompts).lower()

    dimensions = [SHOT_TYPES, FOCUS_TYPES, CAMERA_ANGLES, COMPOSITIONS, SUBJECT_DISTANCES]

    return any(
        not any(_mentions_keyword(combined_text, keyword) for keyword in dimension)
        for dimension in dimensions
    )


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

        if _has_near_duplicate_keywords(subprompts):
            raise ValueError(
                f"서브프롬프트 키워드가 서로 거의 동일합니다: {subprompts!r}"
            )

        if count == len(SHOT_TYPES) and _has_missing_dimension(subprompts):
            raise ValueError(
                f"서브프롬프트에 누락된 다양성 요소가 있습니다: {subprompts!r}"
            )

        return subprompts

    except Exception as exc:
        print(
            f"[SubpromptService] 서브프롬프트 생성 실패, image_prompt로 "
            f"폴백: {exc}"
        )
        return [image_prompt] * count
