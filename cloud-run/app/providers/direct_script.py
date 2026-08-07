"""
Sprint134 - 직접 호출 대본 Provider들이 함께 쓰는 자리 (Epic 56, Phase 11).

Sprint133이 Gemini 하나를 붙였을 때는 글에서 대본을 꺼내고 step01이
읽는 모양으로 싸는 일을 그 파일 안에서 했다. Sprint134에 Claude가
오면서 같은 일이 두 벌이 될 참이었다 - 세 번째부터 조금씩 갈라지고,
그것이 이 저장소가 반복해서 겪은 결함이다.

그래서 갈라지면 안 되는 것만 여기로 모은다.

    ScriptProvider*      예외의 뿌리. 등록소가 두 벌로 잡지 않게
    script_from_text()   글 -> 대본. 펜스·JSON·필수 필드
    build_outcome()      step01이 읽는 모양
    gate_label()         로그 머리말

모으지 않는 것도 있다. 어느 주소로 무슨 머리말을 달아 부르는지는
Provider마다 다르고, 그 차이가 곧 그 Provider다.

여기는 엔진 층이라 app.production을 import하지 않는다
(test_production_architecture가 강제한다).
"""

import json

from app.services import topic_fidelity
from app.services.duration_estimator import estimate_script_duration

# 범위는 게이트가 정한다. 여기 다시 적으면 한쪽만 바뀌는 날이 온다.
from app.services.duration_gate import (
    MAX_ACCEPTABLE_SECONDS,
    MIN_ACCEPTABLE_SECONDS,
    _is_within_range,
)
from app.services import scene_prompt_service

DEFAULT_TARGET_DURATION = 45
DEFAULT_SCENE_COUNT = 6

FENCE = "```"


class ScriptProviderUnavailable(RuntimeError):
    """대본 Provider를 쓸 수 없다.

    설정이 없다. 무엇이 없는지 이름으로 말한다 - 사람이 넣고 다시
    할 수 있어야 한다."""


class ScriptProviderError(RuntimeError):
    """불렀는데 대본을 얻지 못했다.

    모델이 거절했거나, 호출이 실패했거나, 돌아온 것이 대본이 아니다."""


def strip_fence(text: str) -> str:
    """```json 울타리를 걷어낸다. 모델들이 흔히 씌운다."""

    text = (text or "").strip()

    if text.startswith(FENCE):
        text = text.replace("```json", "").replace(FENCE, "").strip()

    return text


def script_from_text(text: str, error=ScriptProviderError) -> dict:
    """
    모델이 쓴 글에서 대본을 꺼낸다.

    실패는 부른 Provider의 예외로 말한다 - "Claude가 거절했다"와
    "대본 형식이 아니다"를 같은 종류로 잡으면 부르는 쪽이 구분하지
    못한다.

    현재 엔진이 만드는 것과 같은 모양이어야 한다 - 뒤 단계가 차이를
    몰라야 하기 때문이다. 그래서 scene 요소를 채우는 것도 엔진이
    거치는 그 서비스를 그대로 쓴다.
    """

    text = strip_fence(text)

    if not text:
        raise error("모델이 빈 답을 돌려주었습니다.")

    try:
        data = json.loads(text)
    except ValueError as exc:
        raise error(
            f"모델이 돌려준 것이 대본 형식이 아닙니다: {exc}"
        ) from exc

    if not isinstance(data, dict) or not data.get("scenes"):
        raise error("모델이 돌려준 대본에 scene이 없습니다.")

    # step02와 스톡 검색이 읽는 필드를 채운다. 여기만 건너뛰면 뒤
    # 단계가 빈 칸을 읽는다.
    data["scenes"] = scene_prompt_service.apply_prompt_elements(
        data["scenes"],
    )

    return data


def gate_label(display_name: str) -> str:
    """
    로그 머리말.

    게이트가 돌지 않았는데 "Duration Gate"라고 적히면 숫자가 참이어도
    로그가 거짓말을 한다.
    """

    return f"{display_name} 직접 호출 · 게이트 없음"


def build_outcome(topic: str, result: dict, label: str) -> dict:
    """
    step01이 읽는 모양으로 싼다.

    Duration Gate가 돌려주는 것과 같은 칸을 쓰되, 값은 전부 실제로
    일어난 것이다.

        attempts          언제나 1. 다시 쓰지 않았다
        estimated_seconds 게이트가 쓰는 그 estimator로 잰 값
        passed            만들어진 대본이 범위 안이고 주제를 지켰는가

    passed는 "게이트가 통과시켰다"가 아니라 관찰이다. 떨어져도 다시
    만들지 않는다 - 그것이 current 엔진과의 차이고, 감출 일이 아니다.
    """

    scenes = result["data"]["scenes"]
    estimated = estimate_script_duration(scenes)

    within_range = _is_within_range(
        estimated, MIN_ACCEPTABLE_SECONDS, MAX_ACCEPTABLE_SECONDS,
    )
    fidelity = topic_fidelity.check(topic, result["data"])

    return {
        "result": result,
        "gate": label,
        "estimated_seconds": estimated,
        "attempts": 1,
        "duration_passed": within_range,
        "topic_fidelity": fidelity,
        "passed": within_range and fidelity["passed"],
    }


def require_topic(topic: str) -> None:
    """
    빈 주제를 모델에 보내지 않는다.

    빈 주제를 받은 모델은 반드시 무언가를 지어내고, 그 대본으로
    이미지와 음성과 영상이 만들어진다 - 아무도 시키지 않은 주제로.
    Provider를 바꿨다고 이 보호까지 사라지면 안 된다.
    """

    topic_fidelity.validate_topic(topic)
