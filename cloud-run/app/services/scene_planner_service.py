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

        plans.append({
            "scene_id": scene_number,
            "purpose": purpose,
            "visual_type": _determine_visual_type(scene),
            "camera": _determine_camera(purpose),
            "transition": assign_transition(scene_number),
            "duration": _estimate_duration(scene.get("narration", "")),
            "keywords": _extract_keywords(scene),
        })

    return plans
