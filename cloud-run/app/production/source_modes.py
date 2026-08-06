"""
Sprint102 - 입력 방식 (Epic 54, Architecture Phase 1).

한 단계의 결과물을 어디서 얻는가.

    GENERATE   API를 불러 만든다. 돈이 든다.
    IMPORT     사용자가 다른 곳에서 만들어 온 것을 받는다.
    MANUAL     사용자가 직접 쓰거나 올린다.

IMPORT를 따로 둔 이유가 있다. 사용자가 GPT/Claude/Gemini/DeepSeek 웹
채팅에서 대본을 만들어 붙여넣는 경로다 - 결과물의 출처는 AI지만 우리가
API를 부르지 않으므로 비용이 0이다. MANUAL(사람이 직접 씀)과 비용
구조는 같지만 출처가 다르고, 붙여넣은 텍스트를 우리 형식으로 파싱해야
한다는 점에서 다루는 방법도 다르다.
"""

GENERATE = "generate"
IMPORT = "import"
MANUAL = "manual"

SOURCE_MODES = (GENERATE, IMPORT, MANUAL)

LABELS = {
    GENERATE: "AI 생성",
    IMPORT: "붙여넣기 / 가져오기",
    MANUAL: "직접 작성 / 업로드",
}

# API를 부르는 방식은 하나뿐이다. 비용 계산과 "Manual은 API 호출 0"
# 계약이 둘 다 이 사실 하나에 기댄다.
BILLABLE_SOURCE_MODES = (GENERATE,)


def is_source_mode(value: str) -> bool:
    return value in SOURCE_MODES


def calls_api(source_mode: str) -> bool:
    return source_mode in BILLABLE_SOURCE_MODES


def require_source_mode(value: str) -> str:
    if not is_source_mode(value):
        raise ValueError(
            f"알 수 없는 입력 방식입니다: {value!r}. "
            f"사용 가능한 값: {list(SOURCE_MODES)}"
        )
    return value
