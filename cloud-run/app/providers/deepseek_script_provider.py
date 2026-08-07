"""
Sprint141 - DeepSeek로 대본을 만든다 (Epic 56, Phase 18).

네 번째이자 마지막 직접 호출 대본 Provider다. 이것이 붙으면 대본
단계에 "자리만 있는" 것이 하나도 남지 않는다.

Sprint134가 공용 자리를 만들어 둔 덕분에 이 파일이 새로 정하는 것은
"어떻게 부르고 어떻게 읽는가" 하나뿐이다 - 글에서 대본을 꺼내는 일도,
step01이 읽는 모양으로 싸는 일도 direct_script가 한다.

current를 대체하지 않는다 - 우회한다
------------------------------------
current는 엔진 전체다.

    Writer          바이럴 템플릿 · 인물 일관성 규칙
    Duration Gate   43~47초를 벗어나면 최대 3회 다시 씀
    Topic Fidelity  주제를 벗어나면 떨어뜨림
    Retry           위 둘이 못 넘기면 가장 가까웠던 것을 고름

이 파일은 모델을 한 번 부르는 것뿐이다.

Chat Completions를 쓴다
-----------------------
DeepSeek는 OpenAI와 같은 모양의 API를 준다. 새 의존성은 더하지
않는다 - FLUX·GPT Image·Claude·OpenAI가 그랬듯 requests로 부른다.

    POST {base}/chat/completions
    Authorization: Bearer

    DEEPSEEK_API_KEY       필수
    DEEPSEEK_API_URL       기본 https://api.deepseek.com
    DEEPSEEK_SCRIPT_MODEL  기본 deepseek-chat

답은 choices[0].message.content에 있다. 추론 모델
(deepseek-reasoner)을 고르면 reasoning_content가 함께 오는데 그것은
생각한 흔적이지 대본이 아니다 - content만 읽는다.

멈춘 이유를 구분한다
--------------------
    content_filter                 안전 기준으로 막혔다 -> 주제를 바꾼다
    length                         한도에 걸려 잘렸다   -> 짧게 요청한다
    insufficient_system_resource   서버가 도중에 멈췄다 -> 다시 해 본다
    stop                           정상

잘린 JSON을 "형식이 아니다"로 말하면 사람이 프롬프트를 고치려 든다.
고칠 곳이 다르므로 글보다 먼저 본다.

확인하지 못한 것
----------------
DEEPSEEK_API_KEY가 없어 실제 왕복을 확인하지 못했다. 주소와 모델은
환경변수로 바꿀 수 있게 둔다.
"""

import os

import requests

from app.prompts.script_prompt import SCRIPT_PROMPT
from app.providers.direct_script import (
    DEFAULT_SCENE_COUNT,
    DEFAULT_TARGET_DURATION,
    ScriptProviderError,
    ScriptProviderUnavailable,
    build_outcome,
    gate_label,
    require_topic,
    script_from_text,
)

DEFAULT_API_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

API_KEY_SETTING = "DEEPSEEK_API_KEY"
MODEL_SETTING = "DEEPSEEK_SCRIPT_MODEL"

REQUEST_TIMEOUT_SECONDS = 180

DISPLAY_NAME = "DeepSeek"

CONTENT_FILTER = "content_filter"
TRUNCATED = "length"
OUT_OF_RESOURCE = "insufficient_system_resource"


class DeepSeekScriptUnavailable(ScriptProviderUnavailable):
    """설정이 없어 DeepSeek를 쓸 수 없다."""


class DeepSeekScriptError(ScriptProviderError):
    """불렀는데 대본을 얻지 못했다."""


def api_url() -> str:
    return (os.getenv("DEEPSEEK_API_URL") or DEFAULT_API_URL).rstrip("/")


def model_id() -> str:
    return os.getenv(MODEL_SETTING) or DEFAULT_MODEL


def _api_key() -> str:
    key = os.getenv(API_KEY_SETTING)

    if not key:
        raise DeepSeekScriptUnavailable(
            f"{API_KEY_SETTING}가 설정되지 않았습니다. "
            "DeepSeek로 대본을 만들려면 그 값이 필요합니다."
        )

    return key


def _rejected(response) -> DeepSeekScriptError:
    """왜 거절당했는지 사람이 읽을 수 있게 만든다."""

    try:
        error = (response.json() or {}).get("error") or {}
    except ValueError:
        error = {}

    detail = error.get("message") or response.text

    return DeepSeekScriptError(
        f"DeepSeek가 요청을 거절했습니다 ({response.status_code}): {detail}"
    )


def _text(payload: dict) -> str:
    """
    답에서 대본 글을 꺼낸다.

    멈춘 이유를 먼저 본다 - 막혔거나 잘렸을 때도 글은 비어 있거나
    깨져 있으므로, 순서를 바꾸면 "대본 형식이 아니다"라는 엉뚱한
    이유를 말하게 된다.
    """

    choices = payload.get("choices") or []

    if not choices:
        raise DeepSeekScriptError("DeepSeek가 답을 돌려주지 않았습니다.")

    choice = choices[0] or {}
    finish = choice.get("finish_reason")

    if finish == CONTENT_FILTER:
        raise DeepSeekScriptError(
            f"DeepSeek가 안전 기준({CONTENT_FILTER})으로 대본을 만들지 "
            "않았습니다. 주제나 표현을 바꾸거나 다른 Provider를 "
            "고르십시오."
        )

    if finish == TRUNCATED:
        raise DeepSeekScriptError(
            f"DeepSeek의 답이 토큰 한도({TRUNCATED})에 걸려 잘렸습니다. "
            "더 짧은 대본을 요청하십시오."
        )

    if finish == OUT_OF_RESOURCE:
        raise DeepSeekScriptError(
            f"DeepSeek가 도중에 멈췄습니다({OUT_OF_RESOURCE}). "
            "잠시 뒤에 다시 해 보십시오."
        )

    message = choice.get("message") or {}

    # 추론 모델은 reasoning_content를 함께 보낸다. 그것은 생각한
    # 흔적이지 대본이 아니므로 읽지 않는다.
    text = (message.get("content") or "").strip()

    if not text:
        if message.get("reasoning_content"):
            raise DeepSeekScriptError(
                "DeepSeek가 생각만 하고 대본을 내놓지 않았습니다."
            )

        raise DeepSeekScriptError("DeepSeek가 빈 답을 돌려주었습니다.")

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

    require_topic(topic)

    key = _api_key()

    prompt = SCRIPT_PROMPT.substitute(
        topic=topic,
        target_duration=target_duration,
        scene_count=scene_count,
    )

    try:
        response = requests.post(
            f"{api_url()}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id(),
                "messages": [{"role": "user", "content": prompt}],
                # 조각으로 오면 대본을 이어 붙이는 일이 새로 생긴다.
                "stream": False,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise DeepSeekScriptError(
            f"DeepSeek 호출이 실패했습니다: {exc}"
        ) from exc

    if response.status_code != 200:
        raise _rejected(response)

    data = script_from_text(_text(response.json() or {}),
                            DeepSeekScriptError)

    print(f"STEP01 DEEPSEEK DIRECT - {model_id()} · "
          f"scenes={len(data['scenes'])}")

    return {"success": True, "data": data}


def script_outcome(topic: str) -> dict:
    """step01이 읽는 모양으로 돌려준다."""

    return build_outcome(
        topic, generate_script(topic), gate_label(DISPLAY_NAME),
    )
