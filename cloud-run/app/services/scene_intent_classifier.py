"""
Sprint101 - Video Intent Intelligence.

scene의 narration/image_prompt를 Gemini(텍스트)에 보여, 실제 Stock
Video 촬영이 자연스러운 내용인지(잠에서 깨는 장면/아침 햇살/운동/
조리 등 - 실사 움직임이 있는 "real world" 장면) 아니면 정지 이미지/
도해가 더 적합한지(의학 설명 등)를 4단계로 판정한다.

이전(Sprint100-3) UploadAssetStrategy.prefers_video()는 한국어
키워드 존재 여부만 보는 좁은 판정이었다("채소"/"섭취"는 안 걸리고
"식사"/"음식"만 걸리는 식) - 이 모듈은 순수 키워드 매칭 대신 LLM
판단으로 그 범위를 넓힌다.

이 파일의 책임은 딱 여기까지다: 입력(narration/image_prompt, 선택적
scene_role/scene_intent) -> Gemini 호출 -> VideoIntentAssessment 파싱
-> VideoIntent 반환. 그 이상은 다루지 않는다 - Asset Selection도,
Motion Contract 최종 결정도, Video Builder 호출도, QA Report 생성도
전부 이 파일 밖(motion_contract.py/asset_integration_service.py/
asset_selector.py/qa_report_service.py)의 책임이다. Rule Override(예:
Conclusion/의학 설명은 이 분류기를 아예 호출하지 않고 규칙으로
고정)도 motion_contract.py가 이 함수를 "언제 호출할지" 판단하는
방식으로 이뤄진다 - 이 함수는 항상 AI 추천만 반환할 뿐, 그 추천을
그대로 최종 정책으로 쓸지는 호출자가 결정한다.

안전장치: Gemini 호출/파싱이 어떤 이유로든 실패해도 예외를 밖으로
던지지 않는다 - 파이프라인이 막히면 안 되므로, 항상 안전한 기본값
(preferred_image, confidence=0.0, source="rule")으로 폴백한다.
"""

from google import genai
from google.genai import types

from app.models.video_intent import VideoIntent, VideoIntentAssessment
from app.prompts.video_intent_rubric import VIDEO_INTENT_RUBRIC


MODEL_NAME = "gemini-2.5-flash"

# Gemini 호출/파싱 실패, 또는 응답은 받았지만 confidence가 너무 낮을
# 때의 안전한 기본값. video를 요구하지 않으므로 항상 안전하게 이미지
# 경로로 계속 진행할 수 있다 - required_image가 아닌 preferred_image인
# 이유는, 판단 불가 상태를 "video를 절대 쓰면 안 된다"는 확정적
# 주장으로 만들지 않기 위함이다(정말 좋은 video 후보가 있다면 여전히
# 선택될 여지를 남긴다).
FALLBACK_INTENT = "preferred_image"

# 이 미만이면 Gemini가 응답은 했지만 판정을 신뢰하기 어렵다고 보고
# FALLBACK_INTENT로 대체한다.
MIN_CONFIDENCE_THRESHOLD = 0.5

client = genai.Client(
    vertexai=True,
    project="wellbeingplant-ai",
    location="global",
)


def classify_video_intent(
    narration: str,
    image_prompt: str,
    scene_role: str = None,
    scene_intent: str = None,
) -> VideoIntent:
    """
    narration/image_prompt(+ 선택적으로 scene_role/scene_intent - 아직
    아무 호출자도 채워 넣지 않지만, 향후 Story Director류 상위 맥락을
    함께 넘길 수 있도록 시그니처만 미리 열어둔다)를 Gemini에 보내
    VideoIntentAssessment로 디코딩한 뒤, VideoIntent(source=
    "ai_classifier")로 변환해 반환한다.

    실패하면(네트워크 오류, 응답 파싱 실패 등) 예외를 던지지 않고
    FALLBACK_INTENT로 안전하게 대체한다 - 이 함수를 호출한 쪽이 항상
    유효한 VideoIntent를 받는다는 계약을 보장한다.
    """

    try:
        scene_context_lines = [
            f"narration: {narration}",
            f"image_prompt: {image_prompt}",
        ]
        if scene_role:
            scene_context_lines.append(f"scene_role: {scene_role}")
        if scene_intent:
            scene_context_lines.append(f"scene_intent: {scene_intent}")

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[VIDEO_INTENT_RUBRIC, "\n".join(scene_context_lines)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoIntentAssessment,
            ),
        )

        if response.parsed is None:
            raise ValueError("no structured response")

        assessment = response.parsed

        if assessment.confidence < MIN_CONFIDENCE_THRESHOLD:
            return VideoIntent(
                intent=FALLBACK_INTENT,
                confidence=assessment.confidence,
                reason=(
                    f"Low confidence ({assessment.confidence:.2f} < "
                    f"{MIN_CONFIDENCE_THRESHOLD}) - 원래 판정: "
                    f"{assessment.intent} ({assessment.reason})"
                ),
                source="rule",
            )

        return VideoIntent(
            intent=assessment.intent,
            confidence=assessment.confidence,
            reason=assessment.reason,
            source="ai_classifier",
        )

    except Exception as exc:
        return VideoIntent(
            intent=FALLBACK_INTENT,
            confidence=0.0,
            reason=f"Gemini unavailable: {exc}",
            source="rule",
        )
