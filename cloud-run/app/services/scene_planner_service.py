"""
Sprint44 - Scene Planner Engine.

완성된 script(Sprint01 script_service가 생성한, scene별 narration/
image_prompt가 이미 채워진 script.json 구조)를 분석해 연출 계획
메타데이터(purpose/visual_type/camera/transition/duration/keywords)를
생성합니다.

이 모듈은 기존 scene 리스트에 필드를 얹는 overlay 방식(transition_engine,
scene_flow_engine)과 달리, 완전히 별도의 계획 리스트(scene_id 기반)를
반환합니다 - 기존 Pipeline/Scene 구조는 이 모듈을 호출하지 않아도
완전히 동일하게 동작해야 한다는 Sprint44 원칙에 따른 것입니다.

Sprint60 - apply_visual_type()은 위 원칙과 무관한 별도 함수입니다.
plan_scenes()의 반환값에도 "visual_type"이라는 키가 있지만(값은
"illustrative"/"photo_realistic", ENABLE_SCENE_PLANNER가 꺼져 있으면
아무데도 쓰이지 않는 선택적 오버레이 메타데이터), apply_visual_type()은
완전히 다른 필드입니다 - scene dict 자체에 "visual_type"("real"/"ai")을
채워 넣고, image 선택 파이프라인(asset_integration_service.py)이 항상
이 값을 읽어 Pexels/Imagen 우선순위를 하드 분기합니다. 두 메커니즘은
이름만 겹칠 뿐 서로 호출하지 않는 독립적인 기능입니다.
"""

import re

from app.services.asset_priority_classifier import classify_scene_importance
from app.services.search_query_extractor import extract_search_query
from app.services.transition_engine import assign_transition
from app.services.visual_type_classifier import apply_visual_type  # noqa: F401

HOOK_PURPOSE = "hook"
CTA_PURPOSE = "cta"
DEVELOPMENT_PURPOSE = "development"

HOOK_CAMERA = "close_up"
CTA_CAMERA = "medium_shot"
DEVELOPMENT_CAMERA = "wide_shot"

CAMERA_BY_PURPOSE = {
    HOOK_PURPOSE: HOOK_CAMERA,
    CTA_PURPOSE: CTA_CAMERA,
}

ILLUSTRATIVE_VISUAL_TYPE = "illustrative"
PHOTO_REALISTIC_VISUAL_TYPE = "photo_realistic"

# 한국어 내레이션 평균 발화 속도 근사치(초당 글자 수). 실제 TTS 오디오
# 길이는 이 시점(스크립트 생성 직후, TTS 실행 전)에는 아직 존재하지
# 않으므로 사용하는 참고용 추정치이며, video_quality_engine 등 실제
# 렌더링 파이프라인의 오디오 기반 duration을 대체하지 않습니다.
KOREAN_NARRATION_CHARS_PER_SECOND = 5.5
MIN_SCENE_DURATION_SECONDS = 2.0

# Sprint69 - Scene Planner v2.
#
# v1은 카메라를 scene 위치만으로 정했다(첫 scene=close_up, 마지막=
# medium_shot, 나머지=wide_shot). 그런데 대본이 만들어 주는 image_prompt는
# 이미 카메라를 지시하고 있는 경우가 많다. 실측 6개 중 3개가 충돌했고,
# "dynamic low-angle close-up shot"에 "wide shot"을 덧붙인 scene은 결과
# 이미지에 뜻 없는 가짜 라벨이 박혔다.
#
# v2는 프롬프트가 이미 말하고 있는 차원은 건드리지 않는다. 아래 패턴으로
# 프롬프트의 프레이밍을 읽어 그대로 채택하고, 어디서 온 값인지를
# camera_source에 남긴다 - prompt_enrichment_service가 그 값을 보고
# "planned"일 때만 문구를 덧붙이므로 충돌은 애초에 생기지 않는다.
#
# 순서가 곧 우선순위는 아니다. 매칭은 프롬프트 안에서 "먼저 나온" 것을
# 주 프레이밍으로 본다 - 사람이 프롬프트를 쓸 때 주 프레이밍을 앞에
# 놓기 때문이다.
CAMERA_PATTERNS = {
    HOOK_CAMERA: (
        r"\bextreme\s+close[-\s]?ups?\b",
        r"\bclose[-\s]?ups?\b",
        r"\bmacro\b",
    ),
    CTA_CAMERA: (
        r"\bmedium[-\s]shots?\b",
        r"\bwaist[-\s]up\b",
        r"\bhalf[-\s]body\b",
    ),
    DEVELOPMENT_CAMERA: (
        r"\bwide[-\s](?:shot|angle)s?\b",
        r"\bestablishing\s+shots?\b",
        r"\bpanoramic\b",
        r"\blong\s+shots?\b",
    ),
}

# 프롬프트가 비주얼 타입을 이미 지시하는 경우도 같은 원칙으로 다룬다.
# 사진 프롬프트에 "illustrative"를 덧붙이면 카메라 충돌과 똑같은 종류의
# 모순이 된다.
VISUAL_TYPE_PATTERNS = {
    PHOTO_REALISTIC_VISUAL_TYPE: (
        r"\bphoto[-\s]?realistic\b",
        r"\bphotorealistic\b",
        r"\bdocumentary\s+photo\b",
    ),
    ILLUSTRATIVE_VISUAL_TYPE: (
        r"\billustrations?\b",
        r"\billustrative\b",
        r"\bdiagram\b",
        r"\bmedical\s+render\b",
        r"\b3d\s+render\b",
    ),
}

PROMPT_SOURCE = "prompt"
PLANNED_SOURCE = "planned"


def _detect_first(image_prompt: str, patterns: dict):
    """
    patterns의 어떤 정규식이 프롬프트에서 가장 먼저 나타나는지 찾아 그
    키를 돌려준다. 아무것도 없으면 None. 순수 함수입니다.
    """

    if not image_prompt:
        return None

    text = image_prompt.lower()

    best_key = None
    best_index = len(text)

    for key, expressions in patterns.items():
        for expression in expressions:
            match = re.search(expression, text)
            if match and match.start() < best_index:
                best_index = match.start()
                best_key = key

    return best_key


def detect_camera(image_prompt: str):
    """
    image_prompt가 이미 지시하고 있는 카메라 프레이밍을 돌려준다.
    지시가 없으면 None. 순수 함수입니다 - 입력을 변경하지 않습니다.
    """

    return _detect_first(image_prompt, CAMERA_PATTERNS)


def detect_visual_type(image_prompt: str):
    """
    image_prompt가 이미 지시하고 있는 비주얼 타입을 돌려준다.
    지시가 없으면 None. 순수 함수입니다.
    """

    return _detect_first(image_prompt, VISUAL_TYPE_PATTERNS)


def _determine_purpose(index: int, total: int) -> str:
    """
    scene 위치만으로 역할을 정합니다 - transition_engine이 hook(첫
    scene)만 구분하는 것과 같은 위치 기반 규칙을 재사용하되, 마지막
    scene에는 cta(행동 유도) 역할을 추가로 부여합니다.
    """

    if index == 0:
        return HOOK_PURPOSE

    if index == total - 1:
        return CTA_PURPOSE

    return DEVELOPMENT_PURPOSE


def _determine_camera(purpose: str) -> str:
    return CAMERA_BY_PURPOSE.get(purpose, DEVELOPMENT_CAMERA)


def _determine_visual_type(scene: dict) -> str:
    """
    Sprint38 asset_priority_classifier.classify_scene_importance()를
    그대로 재사용합니다. AI 우선(prefers_ai) scene은 스톡 사진으로
    대체하기 어려운 주제(해부학/의료 등)라는 뜻이므로 illustrative(도해성)
    비주얼로, 그 외는 실사(photo_realistic) 비주얼로 분류합니다.
    """

    return (
        ILLUSTRATIVE_VISUAL_TYPE
        if classify_scene_importance(scene)["prefers_ai"]
        else PHOTO_REALISTIC_VISUAL_TYPE
    )


def _estimate_duration(narration: str) -> float:

    char_count = len((narration or "").strip())

    if char_count == 0:
        return MIN_SCENE_DURATION_SECONDS

    return round(
        max(
            char_count / KOREAN_NARRATION_CHARS_PER_SECOND,
            MIN_SCENE_DURATION_SECONDS,
        ),
        1,
    )


def _extract_keywords(scene: dict) -> list:
    """
    scene_flow_engine과 동일한 우선순위 - step02_assets가 이미 계산해
    둔 search_query가 있으면 그대로 재사용하고(중복 계산 방지), 없으면
    image_prompt에서 새로 추출합니다.
    """

    query = scene.get("search_query") or extract_search_query(
        scene.get("image_prompt", "")
    )

    return query.split() if query else []


def plan_scenes(script: dict) -> list:
    """
    script(및 그 안의 scenes)를 변경하거나 재정렬하지 않는 순수
    함수입니다. scene 개수만큼 계획 메타데이터 딕셔너리를 원래 scene
    순서 그대로 반환합니다.

    반환값: [{"scene_id": int, "purpose": str, "visual_type": str,
              "camera": str, "transition": str, "duration": float,
              "keywords": list[str]}, ...]
    """

    scenes = (script or {}).get("scenes") or []
    total = len(scenes)

    plans = []

    for index, scene in enumerate(scenes):

        purpose = _determine_purpose(index, total)
        scene_number = scene.get("scene", index + 1)
        image_prompt = scene.get("image_prompt", "")

        # Sprint69 (v2) - 프롬프트가 이미 지시한 것이 있으면 그것을
        # 채택하고, 어디서 왔는지를 함께 남긴다. Enrichment는 planned인
        # 차원만 프롬프트에 덧붙인다.
        stated_camera = detect_camera(image_prompt)
        stated_visual_type = detect_visual_type(image_prompt)

        plans.append({
            "scene_id": scene_number,
            "purpose": purpose,
            "visual_type": stated_visual_type or _determine_visual_type(scene),
            "visual_type_source": (
                PROMPT_SOURCE if stated_visual_type else PLANNED_SOURCE
            ),
            "camera": stated_camera or _determine_camera(purpose),
            "camera_source": (
                PROMPT_SOURCE if stated_camera else PLANNED_SOURCE
            ),
            "transition": assign_transition(scene_number),
            "duration": _estimate_duration(scene.get("narration", "")),
            "keywords": _extract_keywords(scene),
        })

    return plans
