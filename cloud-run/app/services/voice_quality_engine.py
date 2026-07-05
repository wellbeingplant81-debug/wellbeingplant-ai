from app.services.narration_optimizer import optimize_narration
from app.services.smart_pause_engine import apply_smart_pause
from app.services.emphasis_engine import apply_emphasis


def optimize_for_tts(
    narration: str,
    keywords: list = None,
) -> str:
    """
    TTS 합성 직전에만 사용할 임시 문자열을 생성합니다.

    순서: 문장 구조 최적화 -> pause 삽입 -> 강조 처리.
    문장을 먼저 정리한 뒤 pause를 넣어야 마크업이 섞이지 않고,
    강조는 최종 문장 구조가 확정된 뒤 적용해야 위치가 어긋나지 않습니다.

    주의: 이 함수는 원본 narration을 절대 변경하지 않습니다. 반환값은
    TTS 호출에만 사용하고, script.json의 scene["narration"], 자막,
    AI 품질 평가에는 항상 원본 narration을 그대로 사용해야 합니다.
    """

    text = optimize_narration(narration)
    text = apply_smart_pause(text)

    if keywords:
        text = apply_emphasis(text, keywords)

    return text
