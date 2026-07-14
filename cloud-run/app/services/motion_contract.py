"""
Sprint100-2 - Motion Contract.

Scene마다 "이 장면은 어떻게 움직여야 하는가"를 결정하는 순수 판정
모듈. profile="upload"일 때만 의미 있는 값을 반환하고, 그 외
profile(development/default)은 None을 반환해 호출자가 기존 동작을
그대로 유지하게 한다 - 다른 upload-only 모듈(upload_asset_strategy.py)
과 동일한 하위호환 패턴.

이번 스프린트는 motion/max_assets만 실제로 소비된다
(video_builder.py/step02_assets.py가 읽음). hold_seconds/transition은
구조만 갖추고 아직 아무 곳에서도 읽지 않는다 - 다음 스프린트(Scene
Hold Time 실제 강제, Transition Contract)를 위한 확장 지점이다.

Naming collision 참고 (Sprint78~80 패턴과 동일하게 명시): 이 모듈의
"purpose" 값(hook/explanation/conclusion)은 scene_planner_service.py의
"purpose"(hook/development/cta)와 이름만 겹칠 뿐 서로 호출하지 않는
독립적인 필드다.
"""

from app.models.video_intent import VideoIntent
from app.services import scene_intent_classifier
from app.services.upload_asset_strategy import AssetMode, UploadAssetStrategy


MOTION_DYNAMIC = "dynamic"
MOTION_STATIC = "static"
# Sprint100-4까지는 "video를 시도할지"까지 motion 값 하나(video_only)로
# 표현했다. Sprint101부터 그 축은 video_intent 필드(아래)로 완전히
# 분리됐다 - motion은 이제 순수하게 "몇 컷을 쓸지"(dynamic/static)만
# 의미한다. 이 상수는 과거 데이터/호출부와의 하위 호환을 위해 값만
# 남겨두고, build_motion_contract()는 더 이상 이 값을 assign하지
# 않는다.
MOTION_VIDEO_ONLY = "video_only"

PURPOSE_HOOK = "hook"
PURPOSE_EXPLANATION = "explanation"
PURPOSE_CONCLUSION = "conclusion"

INTENT_MEDICAL = "medical"
INTENT_LIFESTYLE = "lifestyle"
INTENT_GENERAL = "general"

# Sprint101 - Video Intent Intelligence. "motion"(컷 수 축)과 별개인
# 새 축 - "이 scene에 실제 Video를 시도할지". scene_intent_classifier.
# classify_video_intent()가 반환하는 VideoIntent.intent 값과 정확히
# 일치해야 한다.
VIDEO_REQUIRED = "required_video"
VIDEO_PREFERRED = "preferred_video"
IMAGE_PREFERRED = "preferred_image"
IMAGE_REQUIRED = "required_image"

# Hold Time: 설명 Scene(static/video_only)에서 asset 하나를 유지할
# 목표 구간(초, 요구사항 4~6초의 중간값). 아직 렌더링에 강제 적용되지
# 않는다 - max_assets=1로 이미 "안 바뀜"은 보장되므로, 이 값은 향후
# narration이 그 구간보다 훨씬 짧거나 긴 경우의 조정 로직을 위한
# 확장 자리다.
DEFAULT_HOLD_SECONDS = 5.0

HOOK_MAX_ASSETS = 3
DEFAULT_MAX_ASSETS = 1


def _determine_purpose(index: int, total: int) -> str:
    if index == 0:
        return PURPOSE_HOOK
    if index == total - 1:
        return PURPOSE_CONCLUSION
    return PURPOSE_EXPLANATION


def _determine_motion(purpose: str, scene: dict) -> tuple:
    """
    반환값: (motion, max_assets, visual_intent, reason)
    """

    if purpose == PURPOSE_HOOK:
        return (
            MOTION_DYNAMIC, HOOK_MAX_ASSETS, INTENT_GENERAL,
            "Hook: Dynamic, 최대 3컷",
        )

    if purpose == PURPOSE_CONCLUSION:
        return (
            MOTION_STATIC, DEFAULT_MAX_ASSETS, INTENT_GENERAL,
            "Conclusion: Static, 이미지 1장",
        )

    if UploadAssetStrategy.select_asset_mode(scene, profile="upload") == AssetMode.AI:
        return (
            MOTION_STATIC, DEFAULT_MAX_ASSETS, INTENT_MEDICAL,
            "Medical Explanation: Static, AI 이미지 1장 고정",
        )

    if UploadAssetStrategy.prefers_video(scene, profile="upload"):
        return (
            MOTION_STATIC, DEFAULT_MAX_ASSETS, INTENT_LIFESTYLE,
            "Lifestyle/Exercise/Food 키워드: Static(1컷) - 실제 Video "
            "시도 여부는 video_intent(Sprint101)가 별도로 판단",
        )

    return (
        MOTION_STATIC, DEFAULT_MAX_ASSETS, INTENT_GENERAL,
        "Explanation(미분류 키워드): Static, 이미지 1장 기본값",
    )


def _determine_video_intent(purpose: str, scene: dict) -> VideoIntent:
    """
    Sprint101 - Rule Engine. "이 scene에 실제 Video를 시도할지"의
    유일한 판단처. Rule Override 구조: 아래 두 하드코딩 규칙이 항상
    AI 분류기보다 우선한다(분류기 자체를 호출조차 하지 않는다) -
    scene_intent_classifier.classify_video_intent()는 "AI 추천"일
    뿐, 최종 정책은 이 함수(Rule Engine)가 정한다.

    1. Conclusion은 항상 required_image다 - Sprint100-3에서 실측된
       버그(Conclusion인데 실제로는 Video로 렌더링됨)의 재발을
       구조적으로 막는다.
    2. 의학/해부학 설명(UploadAssetStrategy.select_asset_mode==AI)도
       항상 required_image다 - 혈관 단면 등은 실제 촬영이 불가능한
       도해이므로, AI 판단에 맡길 필요 없이 확정적이다.

    그 외(Hook 포함)는 scene_intent_classifier.classify_video_intent()
    를 호출한다 - 이 함수는 실패해도 예외를 던지지 않고 항상 안전한
    VideoIntent를 반환하므로, 여기서 별도 예외 처리를 하지 않는다.
    """

    if purpose == PURPOSE_CONCLUSION:
        return VideoIntent(
            intent=IMAGE_REQUIRED,
            confidence=1.0,
            reason="Conclusion: 항상 정적 이미지(Sprint100-3 SSoT 회귀 방지)",
            source="rule",
        )

    if UploadAssetStrategy.select_asset_mode(scene, profile="upload") == AssetMode.AI:
        return VideoIntent(
            intent=IMAGE_REQUIRED,
            confidence=1.0,
            reason="의학/해부학 설명: AI 이미지 필수",
            source="rule",
        )

    return scene_intent_classifier.classify_video_intent(
        scene.get("narration", ""), scene.get("image_prompt", ""),
    )


def allows_video(video_intent: str) -> bool:
    """
    Sprint100-4 - Visual Intelligence Completion. Sprint101부터는
    motion 값이 아니라 video_intent 값(required_video/preferred_video/
    preferred_image/required_image)을 받는다 - Asset Selection이
    Stock Video 후보를 아예 요청해도 되는지를 결정하는 유일한 판단처.
    required_image가 아니면 전부 True다(preferred_image도 Video 후보
    자체는 받되, 실제 승자는 Visual Relevance 점수로만 정해진다 -
    "Image보다 더 자연스러우면 Video를 선택").

    Why: 2026-07-14 Production QA에서, motion=static/dynamic인 scene도
    일반 랭킹(select_best_with_score)에서 Stock Video가 1위를 하면
    Visual Relevance 검증 없이 곧바로 채택되어, Hook scene이 나레이션과
    무관한 헤어 클로즈업으로 렌더링되는 사고가 실측됐다. Motion
    Contract가 "Video를 고려할지" 자체를 먼저 결정하게 하면 이 경로가
    구조적으로 막힌다.
    """

    return video_intent != IMAGE_REQUIRED


def index_by_scene_id(contract: list) -> dict:
    """
    Sprint100-3 - build_motion_contract()의 결과를 scene_id -> entry
    dict로 재색인한다. 오케스트레이션(step02_assets.py)이 scene마다
    O(1)로 조회할 수 있게 하는 순수 데이터 변환일 뿐, 새 판정 로직은
    없다.
    """

    return {entry["scene_id"]: entry for entry in (contract or [])}


def video_priority_scene_ids(contract: list) -> set:
    """
    Sprint100-3 - Motion Contract Single Source of Truth. contract의
    video_intent가 required_video/preferred_video인 scene_id 집합을
    반환한다(Sprint101부터 motion=="video_only" 체크에서 video_intent
    체크로 이관 - motion은 이제 컷 수 축일 뿐 video 여부를 담지 않는다).

    이전에는 step02_assets.py가 UploadAssetStrategy.prefers_video()를
    scene 전체에 대해 별도로 다시 호출해 video 우선 scene 집합을
    독자적으로 계산했다 - Motion Contract가 Hook/Conclusion을 motion=
    dynamic/static으로 위치 기반 오버라이드해도 그 별도 호출은 이
    오버라이드를 모르고 그대로 video를 우선시켜버렸다(실측: Conclusion
    scene이 motion_contract="static"인데 실제로는 video로 렌더링됨,
    2026-07-14 Production QA). 이제 이 함수가 "어떤 scene이 video를
    우선해야 하는가"의 유일한 판단처다 - step02_assets.py는 이 결과를
    그대로 쓸 뿐 video/static/dynamic을 다시 판단하지 않는다.
    """

    return {
        entry["scene_id"] for entry in (contract or [])
        if entry["video_intent"]["intent"] in (VIDEO_REQUIRED, VIDEO_PREFERRED)
    }


def build_motion_contract(scenes: list, profile: str = None) -> list:
    """
    scenes(script.json의 scene 리스트)를 변경하지 않는 함수.

    profile != "upload"면 None을 반환한다 - "Motion Contract 자체가
    적용되지 않음"을 빈 scenes([])와 구분하기 위함이다.

    Sprint101 - Video Intent Intelligence. 각 entry에 video_intent
    (VideoIntent.model_dump() - intent/confidence/reason/source)를
    추가한다. _determine_video_intent()(Rule Engine)가 Conclusion/
    의학 설명은 분류기 호출 없이 즉시 확정하고, 그 외에는 scene_
    intent_classifier.classify_video_intent()(AI 추천)를 호출한 뒤
    그 결과를 그대로 최종 정책으로 채택한다 - "AI는 추천, 최종 결정은
    Rule Engine"이라는 원칙은 하드코딩된 두 규칙이 분류기보다 먼저
    검사되어 분류기 호출 자체를 막아버리는 방식으로 구현된다(분류기
    결과를 받은 뒤 다시 뒤집는 후처리가 아니다).

    Sprint100-2 이후 이 함수는 순수 함수였지만, Hook/Explanation
    scene마다 실제 Gemini 호출이 발생하므로 이제는 네트워크 I/O를
    수행하며 scene 개수만큼 순차적으로 느려질 수 있다(개별 실패는
    scene_intent_classifier.py 자체의 안전한 폴백으로 흡수되어 예외를
    던지지 않는다).
    """

    if profile != "upload":
        return None

    total = len(scenes)
    contract = []

    for index, scene in enumerate(scenes):

        purpose = _determine_purpose(index, total)
        motion, max_assets, visual_intent, reason = _determine_motion(purpose, scene)
        video_intent = _determine_video_intent(purpose, scene)

        contract.append({
            "scene_id": scene.get("scene", index + 1),
            "purpose": purpose,
            "visual_intent": visual_intent,
            "motion": motion,
            "max_assets": max_assets,
            "hold_seconds": (
                DEFAULT_HOLD_SECONDS if motion != MOTION_DYNAMIC else None
            ),
            "transition": None,
            "reason": reason,
            "video_intent": video_intent.model_dump(),
        })

    return contract
