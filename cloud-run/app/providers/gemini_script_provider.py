"""
Sprint133 - Gemini로 대본을 만든다 (Epic 56, Phase 10).

Sprint128이 놓은 다리에 처음으로 도착하는 실제 Script Provider다.
그전까지 script_provider는 이름만 날랐고 도착지에서 전부 거절했다.

current를 대체하지 않는다 - 우회한다
------------------------------------
current는 엔진 전체다.

    Writer          바이럴 템플릿 · 인물 일관성 규칙
    Duration Gate   43~47초를 벗어나면 최대 3회 다시 씀
    Topic Fidelity  주제를 벗어나면 떨어뜨림
    Retry           위 둘이 못 넘기면 가장 가까웠던 것을 고름

이 파일은 모델을 한 번 부르는 것뿐이다. 같은 gemini-2.5-pro를
부르더라도 거치는 것이 다르므로 결과가 같지 않다.

인증부터 다른 길이다
--------------------
current는 Vertex AI로 간다 - genai.Client(vertexai=True, project=...)
이고, 자격은 환경에 붙은 것(ADC)을 쓴다. 이쪽은 API 키로 모델을 직접
부른다. "파이프라인을 거치지 않고 모델을 직접 부르는 쪽"이라는 말이
인증 경로에서부터 사실이다.

    GOOGLE_API_KEY        필수
    GEMINI_SCRIPT_MODEL   기본 gemini-2.5-pro

가져다 쓰는 것과 안 쓰는 것
---------------------------
    쓴다     SCRIPT_PROMPT          대본의 모양을 정하는 계약
             apply_prompt_elements  step02가 읽는 필드를 채운다
             validate_topic         빈 주제를 모델에 보내지 않는다
             estimate / check       만든 것을 재서 보고한다
    안 쓴다  재생성 루프            한 번만 부른다
             바이럴 템플릿 · 인물 규칙   current의 품질 층이다

재는 것과 고쳐 만드는 것은 다른 일이다. 이 Provider는 앞엣것만 한다 -
그래서 script_outcome이 돌려주는 passed는 "게이트가 통과시켰다"가
아니라 "만들어진 대본이 그 범위 안에 있다"는 관찰이고, attempts는
언제나 1이다. 세 번 시도한 척하지 않는다.

층 경계
-------
여기는 엔진 층이라 app.production을 import하지 않는다
(test_production_architecture가 강제한다). 등록소에 올라가는
StageProvider는 app/production/providers/gemini_script.py가 맡고,
이 모듈을 감싸기만 한다.
"""

import json
import os

from google import genai

from app.prompts.script_prompt import SCRIPT_PROMPT
from app.services import scene_prompt_service, topic_fidelity
from app.services.duration_estimator import estimate_script_duration

# 범위는 게이트가 정한다. 여기 다시 적으면 한쪽만 바뀌는 날이 온다.
from app.services.duration_gate import (
    MAX_ACCEPTABLE_SECONDS,
    MIN_ACCEPTABLE_SECONDS,
    _is_within_range,
)

API_KEY_SETTING = "GOOGLE_API_KEY"
MODEL_SETTING = "GEMINI_SCRIPT_MODEL"

# 현재 엔진이 부르는 것과 같은 모델이다. 거치는 것이 다를 뿐이다.
DEFAULT_MODEL = "gemini-2.5-pro"

DEFAULT_TARGET_DURATION = 45
DEFAULT_SCENE_COUNT = 6

# 모델이 말을 멈춘 이유 중 "만들지 않기로 했다"에 해당하는 것들.
# 부르는 쪽이 고칠 수 있는 일이므로 망가진 호출과 구분해서 말한다.
BLOCKED_FINISH_REASONS = (
    "SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION", "SPII",
)

FENCE = "```"

# 로그 머리말. 게이트가 돌지 않았다는 것을 로그가 그대로 말해야 한다.
GATE_LABEL = "Gemini 직접 호출 · 게이트 없음"


class GeminiScriptUnavailable(RuntimeError):
    """Gemini를 쓸 수 없다.

    설정이 없다. 무엇이 없는지 이름으로 말한다 - 사람이 넣고 다시
    할 수 있어야 한다."""


class GeminiScriptError(RuntimeError):
    """불렀는데 대본을 얻지 못했다.

    모델이 거절했거나, 호출이 실패했거나, 돌아온 것이 대본이 아니다."""


def model_id() -> str:
    return os.getenv(MODEL_SETTING) or DEFAULT_MODEL


def _api_key() -> str:
    key = os.getenv(API_KEY_SETTING)

    if not key:
        raise GeminiScriptUnavailable(
            f"{API_KEY_SETTING}가 설정되지 않았습니다. "
            "Gemini로 대본을 만들려면 그 값이 필요합니다."
        )

    return key


def _blocked(response):
    """모델이 만들지 않기로 한 이유. 아니면 None."""

    feedback = getattr(response, "prompt_feedback", None)
    reason = getattr(feedback, "block_reason", None)

    if reason:
        message = getattr(feedback, "block_reason_message", "") or ""
        return f"요청이 막혔습니다({reason}). {message}".strip()

    for candidate in getattr(response, "candidates", None) or []:
        finish = getattr(candidate, "finish_reason", None)
        name = getattr(finish, "name", finish)

        if name and str(name) in BLOCKED_FINISH_REASONS:
            return f"모델이 답을 중간에 멈췄습니다({name})."

    return None


def _text(response) -> str:
    """
    응답에서 대본 글을 꺼낸다.

    막힌 것을 먼저 본다 - 막혔을 때도 text는 비어 있으므로, 순서를
    바꾸면 "빈 답"이라는 엉뚱한 이유를 말하게 된다.
    """

    blocked = _blocked(response)

    if blocked:
        raise GeminiScriptError(
            f"Gemini가 대본을 만들지 않았습니다: {blocked} "
            "주제나 표현을 바꾸거나 다른 Provider를 고르십시오."
        )

    text = (getattr(response, "text", None) or "").strip()

    if not text:
        raise GeminiScriptError("Gemini가 빈 답을 돌려주었습니다.")

    if text.startswith(FENCE):
        text = text.replace("```json", "").replace(FENCE, "").strip()

    return text


def generate_script(
    topic: str,
    target_duration: int = DEFAULT_TARGET_DURATION,
    scene_count: int = DEFAULT_SCENE_COUNT,
) -> dict:
    """
    대본을 한 번 만든다. 현재 엔진의 generate_script와 같은 모양으로
    돌려준다 - 뒤 단계가 차이를 몰라야 한다.

    다시 쓰지 않는다. 길이가 어긋나도, 주제를 벗어나도 그대로
    돌려준다 - 그 판단과 재생성은 current 엔진의 일이다.
    """

    # 빈 주제를 받은 모델은 반드시 무언가를 지어내고, 그 대본으로
    # 이미지와 음성과 영상이 만들어진다. Provider를 바꿨다고 이
    # 보호까지 사라지면 안 된다.
    topic_fidelity.validate_topic(topic)

    key = _api_key()

    prompt = SCRIPT_PROMPT.substitute(
        topic=topic,
        target_duration=target_duration,
        scene_count=scene_count,
    )

    try:
        response = genai.Client(api_key=key).models.generate_content(
            model=model_id(),
            contents=prompt,
        )
    except Exception as exc:
        raise GeminiScriptError(
            f"Gemini 호출이 실패했습니다: {exc}"
        ) from exc

    text = _text(response)

    try:
        data = json.loads(text)
    except ValueError as exc:
        raise GeminiScriptError(
            f"Gemini가 돌려준 것이 대본 형식이 아닙니다: {exc}"
        ) from exc

    if not isinstance(data, dict) or not data.get("scenes"):
        raise GeminiScriptError("Gemini가 돌려준 대본에 scene이 없습니다.")

    # step02와 스톡 검색이 읽는 필드를 채운다. 현재 엔진이 거치는 그
    # 서비스를 그대로 쓴다 - 여기만 건너뛰면 뒤 단계가 빈 칸을 읽는다.
    data["scenes"] = scene_prompt_service.apply_prompt_elements(
        data["scenes"],
    )

    print(f"STEP01 GEMINI DIRECT - {model_id()} · scenes={len(data['scenes'])}")

    return {"success": True, "data": data}


def script_outcome(topic: str) -> dict:
    """
    step01이 읽는 모양으로 돌려준다.

    Duration Gate가 돌려주는 것과 같은 칸을 쓰되, 값은 전부 실제로
    일어난 것이다.

        attempts          언제나 1. 다시 쓰지 않았다
        estimated_seconds 게이트가 쓰는 그 estimator로 잰 값
        passed            만들어진 대본이 범위 안이고 주제를 지켰는가

    passed는 "게이트가 통과시켰다"가 아니라 관찰이다. 떨어져도 다시
    만들지 않는다 - 그것이 current 엔진과의 차이고, 감출 일이 아니다.
    """

    result = generate_script(topic)

    scenes = result["data"]["scenes"]
    estimated = estimate_script_duration(scenes)

    within_range = _is_within_range(
        estimated, MIN_ACCEPTABLE_SECONDS, MAX_ACCEPTABLE_SECONDS,
    )
    fidelity = topic_fidelity.check(topic, result["data"])

    return {
        "result": result,
        # step01이 로그 머리말로 쓴다. 게이트가 돌지 않았는데 "Duration
        # Gate"라고 적히면 로그가 사실이 아닌 말을 하게 된다.
        "gate": GATE_LABEL,
        "estimated_seconds": estimated,
        "attempts": 1,
        "duration_passed": within_range,
        "topic_fidelity": fidelity,
        "passed": within_range and fidelity["passed"],
    }
