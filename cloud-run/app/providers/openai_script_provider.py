"""
Sprint135 - OpenAI로 대본을 만든다 (Epic 56, Phase 12).

세 번째 실제 Script Provider다. Sprint134가 공용 자리를 만들어 둔
덕분에 이 파일이 새로 정하는 것은 "어떻게 부르고 어떻게 읽는가"
하나뿐이다 - 글에서 대본을 꺼내는 일도, step01이 읽는 모양으로 싸는
일도 direct_script가 한다.

current를 대체하지 않는다 - 우회한다
------------------------------------
current는 엔진 전체다.

    Writer          바이럴 템플릿 · 인물 일관성 규칙
    Duration Gate   43~47초를 벗어나면 최대 3회 다시 씀
    Topic Fidelity  주제를 벗어나면 떨어뜨림
    Retry           위 둘이 못 넘기면 가장 가까웠던 것을 고름

이 파일은 모델을 한 번 부르는 것뿐이다.

Responses API를 쓴다
--------------------
이 저장소는 이미 OpenAI를 부른다 - Sprint131의 GPT Image가 같은
호스트에 같은 Bearer 인증으로 간다. 키도 같은 것을 읽는다. 두 이름을
쓰면 하나만 넣고 나머지가 왜 안 되는지 모르게 된다.

    POST {base}/v1/responses

    OPENAI_API_KEY       필수 (GPT Image와 같은 키)
    OPENAI_API_URL       기본 https://api.openai.com
    OPENAI_SCRIPT_MODEL  기본 gpt-5

답의 모양이 Gemini·Claude와 다르다
----------------------------------
글은 output 배열 안의 message 항목에, 그 안 output_text 조각에 있다.
output에는 message가 아닌 것도 들어온다 - 추론 모델은 reasoning
항목을 함께 넣는다. 걸러내지 않으면 대본이 아닌 것을 읽게 된다.

멈춘 이유도 두 곳으로 나뉜다.

    refusal 조각              모델이 쓰지 않기로 했다 -> 주제를 바꾼다
    status=incomplete
      content_filter          안전 기준에 걸렸다
      max_output_tokens       한도에 걸려 잘렸다     -> 한도를 올린다

잘린 JSON을 "형식이 아니다"로 말하면 사람이 프롬프트를 고치려 든다.
고칠 곳은 한도다. 그래서 글보다 먼저 본다.

확인하지 못한 것
----------------
OPENAI_API_KEY가 없어 실제 왕복을 확인하지 못했다. 모델 이름과 주소는
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

DEFAULT_API_URL = "https://api.openai.com"
DEFAULT_MODEL = "gpt-5"

# GPT Image(Sprint131)가 읽는 것과 같은 이름이다. 같은 회사의 같은
# 키이므로 따로 두지 않는다 - 테스트가 둘을 잠근다.
API_KEY_SETTING = "OPENAI_API_KEY"
MODEL_SETTING = "OPENAI_SCRIPT_MODEL"

REQUEST_TIMEOUT_SECONDS = 180

DISPLAY_NAME = "OpenAI"

INCOMPLETE = "incomplete"
CONTENT_FILTER = "content_filter"
TRUNCATED = "max_output_tokens"

MESSAGE = "message"
OUTPUT_TEXT = "output_text"
REFUSAL = "refusal"


class OpenAIScriptUnavailable(ScriptProviderUnavailable):
    """설정이 없어 OpenAI를 쓸 수 없다."""


class OpenAIScriptError(ScriptProviderError):
    """불렀는데 대본을 얻지 못했다."""


def api_url() -> str:
    return (os.getenv("OPENAI_API_URL") or DEFAULT_API_URL).rstrip("/")


def model_id() -> str:
    return os.getenv(MODEL_SETTING) or DEFAULT_MODEL


def _api_key() -> str:
    key = os.getenv(API_KEY_SETTING)

    if not key:
        raise OpenAIScriptUnavailable(
            f"{API_KEY_SETTING}가 설정되지 않았습니다. "
            "OpenAI로 대본을 만들려면 그 값이 필요합니다."
        )

    return key


def _rejected(response) -> OpenAIScriptError:
    """왜 거절당했는지 사람이 읽을 수 있게 만든다."""

    try:
        error = (response.json() or {}).get("error") or {}
    except ValueError:
        error = {}

    detail = error.get("message") or response.text

    return OpenAIScriptError(
        f"OpenAI가 요청을 거절했습니다 ({response.status_code}): {detail}"
    )


def _parts(payload: dict):
    """
    답에서 글 조각과 거절 조각을 모은다.

    message가 아닌 항목은 건너뛴다 - 추론 모델이 넣는 reasoning은
    대본이 아니다.
    """

    texts = []
    refusals = []

    for item in payload.get("output") or []:
        if item.get("type") != MESSAGE:
            continue

        for part in item.get("content") or []:
            kind = part.get("type")

            if kind == OUTPUT_TEXT:
                texts.append(part.get("text") or "")
            elif kind == REFUSAL:
                refusals.append(part.get(REFUSAL) or "")

    return texts, refusals


def _text(payload: dict) -> str:
    """
    답에서 대본 글을 꺼낸다.

    멈춘 이유를 먼저 본다 - 거절당했거나 잘렸을 때도 글은 비어 있거나
    깨져 있으므로, 순서를 바꾸면 "대본 형식이 아니다"라는 엉뚱한
    이유를 말하게 된다.
    """

    if payload.get("status") == INCOMPLETE:
        reason = (payload.get("incomplete_details") or {}).get("reason")

        if reason == TRUNCATED:
            raise OpenAIScriptError(
                f"OpenAI의 답이 {TRUNCATED} 한도에 걸려 잘렸습니다. "
                "더 짧은 대본을 요청하거나 한도를 올리십시오."
            )

        if reason == CONTENT_FILTER:
            raise OpenAIScriptError(
                f"OpenAI가 안전 기준({CONTENT_FILTER})으로 답을 멈췄습니다. "
                "주제나 표현을 바꾸거나 다른 Provider를 고르십시오."
            )

        raise OpenAIScriptError(
            f"OpenAI가 답을 끝내지 못했습니다({reason})."
        )

    texts, refusals = _parts(payload)

    text = "".join(texts)

    if not text.strip():
        if refusals:
            raise OpenAIScriptError(
                "OpenAI가 대본 쓰기를 거절했습니다: "
                f"{' '.join(r for r in refusals if r)} "
                "주제나 표현을 바꾸거나 다른 Provider를 고르십시오."
            )

        raise OpenAIScriptError("OpenAI가 빈 답을 돌려주었습니다.")

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
            f"{api_url()}/v1/responses",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id(),
                "input": prompt,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise OpenAIScriptError(
            f"OpenAI 호출이 실패했습니다: {exc}"
        ) from exc

    if response.status_code != 200:
        raise _rejected(response)

    data = script_from_text(_text(response.json() or {}), OpenAIScriptError)

    print(f"STEP01 OPENAI DIRECT - {model_id()} · scenes={len(data['scenes'])}")

    return {"success": True, "data": data}


def script_outcome(topic: str) -> dict:
    """step01이 읽는 모양으로 돌려준다."""

    return build_outcome(
        topic, generate_script(topic), gate_label(DISPLAY_NAME),
    )
