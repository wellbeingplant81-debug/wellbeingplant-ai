"""
Sprint134 - Claude로 대본을 만든다 (Epic 56, Phase 11).

Sprint133의 Gemini에 이어 두 번째 실제 Script Provider다. 다리는
Sprint128에 놓였으므로 이번에 하는 일은 도착지 하나를 더 여는 것이다.

current를 대체하지 않는다 - 우회한다
------------------------------------
current는 엔진 전체다.

    Writer          바이럴 템플릿 · 인물 일관성 규칙
    Duration Gate   43~47초를 벗어나면 최대 3회 다시 씀
    Topic Fidelity  주제를 벗어나면 떨어뜨림
    Retry           위 둘이 못 넘기면 가장 가까웠던 것을 고름

이 파일은 모델을 한 번 부르는 것뿐이다.

새 의존성을 더하지 않는다
-------------------------
anthropic 패키지는 이 저장소에 없다. 대본 하나를 만들자고 의존성을
늘릴 이유가 없으므로 FLUX·GPT Image가 그랬듯 requests로 Messages API를
직접 부른다.

    POST {base}/v1/messages
    x-api-key · anthropic-version

한 번에 끝난다 - 폴링이 없다. 대신 그 한 번이 길어서 넉넉히 기다린다.

    ANTHROPIC_API_KEY     필수
    ANTHROPIC_API_URL     기본 https://api.anthropic.com
    CLAUDE_SCRIPT_MODEL   기본 claude-sonnet-5
    CLAUDE_MAX_TOKENS     기본 8000

모델은 세대 중 균형점을 기본으로 둔다. 6 scene짜리 짧은 대본이라
더 큰 모델이 필요하다고 볼 근거가 아직 없다 - 재 본 적이 없으므로
지어내지 않는다. 바꾸고 싶으면 CLAUDE_SCRIPT_MODEL로 올리면 된다
(예: claude-opus-5).

멈춘 이유를 구분한다
--------------------
Messages API는 왜 멈췄는지 stop_reason으로 말한다. 이것을 뭉뚱그리면
사람이 엉뚱한 곳을 고친다.

    refusal     안전 기준으로 거절했다  -> 주제·표현을 바꾼다
    max_tokens  한도에 걸려 잘렸다      -> 한도를 올린다
    end_turn    정상

잘린 JSON을 "형식이 아니다"로 말하면 프롬프트를 고치려 들게 된다.
고칠 곳은 한도다.

확인하지 못한 것
----------------
ANTHROPIC_API_KEY가 없어 실제 왕복을 확인하지 못했다. 주소와 모델은
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

DEFAULT_API_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-sonnet-5"

# Messages API가 요구하는 머리말. 없으면 거절한다.
API_VERSION = "2023-06-01"

API_KEY_SETTING = "ANTHROPIC_API_KEY"
MODEL_SETTING = "CLAUDE_SCRIPT_MODEL"

# 6 scene 대본 JSON이 들어갈 만큼. 모자라면 잘린 채로 돌아오므로
# 넉넉히 두고, 모자랄 때는 그 사실을 그대로 말한다.
DEFAULT_MAX_TOKENS = 8000

REQUEST_TIMEOUT_SECONDS = 180

DISPLAY_NAME = "Claude"

REFUSAL = "refusal"
TRUNCATED = "max_tokens"


class ClaudeScriptUnavailable(ScriptProviderUnavailable):
    """설정이 없어 Claude를 쓸 수 없다."""


class ClaudeScriptError(ScriptProviderError):
    """불렀는데 대본을 얻지 못했다."""


def api_url() -> str:
    return (os.getenv("ANTHROPIC_API_URL") or DEFAULT_API_URL).rstrip("/")


def model_id() -> str:
    return os.getenv(MODEL_SETTING) or DEFAULT_MODEL


def max_tokens() -> int:
    try:
        return int(os.getenv("CLAUDE_MAX_TOKENS") or DEFAULT_MAX_TOKENS)
    except ValueError:
        return DEFAULT_MAX_TOKENS


def _api_key() -> str:
    key = os.getenv(API_KEY_SETTING)

    if not key:
        raise ClaudeScriptUnavailable(
            f"{API_KEY_SETTING}가 설정되지 않았습니다. "
            "Claude로 대본을 만들려면 그 값이 필요합니다."
        )

    return key


def _refused(response) -> ClaudeScriptError:
    """왜 거절당했는지 사람이 읽을 수 있게 만든다."""

    try:
        error = (response.json() or {}).get("error") or {}
    except ValueError:
        error = {}

    detail = error.get("message") or response.text

    return ClaudeScriptError(
        f"Claude가 요청을 거절했습니다 ({response.status_code}): {detail}"
    )


def _text(payload: dict) -> str:
    """
    답에서 글을 꺼낸다.

    멈춘 이유를 먼저 본다 - 거절당했거나 잘렸을 때도 글은 비어 있거나
    깨져 있으므로, 순서를 바꾸면 "대본 형식이 아니다"라는 엉뚱한
    이유를 말하게 된다.
    """

    stop_reason = payload.get("stop_reason")

    if stop_reason == REFUSAL:
        raise ClaudeScriptError(
            "Claude가 안전 기준에 따라 대본 쓰기를 거절했습니다. "
            "주제나 표현을 바꾸거나 다른 Provider를 고르십시오."
        )

    if stop_reason == TRUNCATED:
        raise ClaudeScriptError(
            f"Claude의 답이 {TRUNCATED} 한도에 걸려 잘렸습니다"
            f"(지금 {max_tokens()}). CLAUDE_MAX_TOKENS를 올리십시오."
        )

    # 글 조각이 여럿으로 나뉘어 올 수 있다. 첫 조각만 읽으면 대본
    # 절반으로 JSON을 파싱하게 된다.
    text = "".join(
        block.get("text") or ""
        for block in payload.get("content") or []
        if block.get("type") == "text"
    )

    if not text.strip():
        raise ClaudeScriptError("Claude가 빈 답을 돌려주었습니다.")

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
            f"{api_url()}/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model_id(),
                "max_tokens": max_tokens(),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise ClaudeScriptError(
            f"Claude 호출이 실패했습니다: {exc}"
        ) from exc

    if response.status_code != 200:
        raise _refused(response)

    data = script_from_text(_text(response.json() or {}),
                            ClaudeScriptError)

    print(f"STEP01 CLAUDE DIRECT - {model_id()} · scenes={len(data['scenes'])}")

    return {"success": True, "data": data}


def script_outcome(topic: str) -> dict:
    """step01이 읽는 모양으로 돌려준다."""

    return build_outcome(
        topic, generate_script(topic), gate_label(DISPLAY_NAME),
    )
