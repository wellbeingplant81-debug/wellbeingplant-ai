from pydantic import BaseModel


class VideoIntent(BaseModel):
    """
    Sprint101 - Video Intent Intelligence. 순수 데이터 모델이다 -
    Asset Selection/Motion 정책/Video Builder 판단 로직은 여기 넣지
    않는다(그건 각각 asset_integration_service.py/motion_contract.py/
    video_builder.py의 책임).

    intent: "required_video" | "preferred_video" | "preferred_image" |
        "required_image" (motion_contract.py의 상수와 매칭)
    confidence: 0.0~1.0
    reason: 이 판정을 내린 이유(한국어)
    source: 이 판정이 어디서 나왔는지 - "ai_classifier"(Gemini 분류기
        실제 호출) | "hardcoded_conclusion" | "hardcoded_medical" |
        "keyword_fallback"(분류기 호출 실패 시 안전망)
    """

    intent: str
    confidence: float
    reason: str
    # "ai_classifier"(Gemini 분류기 실제 호출 성공) | "rule"(motion_
    # contract.py의 하드코딩 규칙, 또는 Gemini 호출 실패 시 scene_
    # intent_classifier.py의 안전한 기본값 폴백) 둘 중 하나.
    source: str


class VideoIntentAssessment(BaseModel):
    """
    Sprint101 - scene_intent_classifier.py가 Gemini 구조화 응답을
    디코딩하는 데만 쓰는 원본 스키마다. video_intent_rubric.py가
    요구하는 3개 필드(intent/confidence/reason)를 그대로 받는다 -
    VideoIntent(도메인 모델)로 변환하기 전 단계일 뿐인 순수 데이터
    컨테이너다.
    """

    intent: str
    confidence: float
    reason: str
