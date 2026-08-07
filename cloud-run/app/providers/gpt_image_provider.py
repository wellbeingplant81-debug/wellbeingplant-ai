"""
Sprint131 - GPT Image로 이미지 한 장을 만든다 (Epic 56, Phase 8).

Sprint130의 FLUX에 이어 두 번째로 실제로 붙는 이미지 Provider다.
다리는 Sprint127에 놓였으므로 이번에 하는 일은 도착지 하나를 더 여는
것뿐이다.

current를 대체하지 않는다. current는 Best-of-N · 품질 게이트 ·
Pexels 폴백 · 재시도까지 붙은 엔진 전체이고, 이 파일은 이미지 한 장을
만드는 것뿐이다.

FLUX보다 단순하다
-----------------
FLUX는 비동기라 제출 -> 폴링 -> 내려받기 세 걸음이었다. 이쪽은 한 번에
끝난다.

    POST {base}/v1/images/generations   -> 응답 안에 이미지가 들어 있다

이미지가 주소가 아니라 base64로 담겨 오므로 따로 내려받을 곳이 없다.
다만 모델을 바꾸면 주소로 오는 것도 있어서 둘 다 받는다.

한 번에 끝나는 대신 그 한 번이 길다. 그래서 기다리는 시간을 넉넉히
잡는다 - 짧게 잡으면 만들어진 이미지를 버리게 된다.

크기를 숫자로 고를 수 없다
--------------------------
FLUX는 가로·세로를 정할 수 있었지만 OpenAI는 정해진 값 중에서만
고른다. 세로 중 가장 큰 것이 1024x1536이고 이것은 2:3이다 -
파이프라인의 9:16이 아니다.

늘어나지는 않는다. kenburns._fit_scale이 1080x1920을 덮는 배율로 키운
뒤 넘치는 만큼 잘라내기 때문이다(cover). 다만 얼마나 잘리는지가 다르다.

    현재 엔진 768x1408  -> 1081x1982   세로 3.1% 잘림
    여기      1024x1536 -> 1281x1922   가로 15.7% 잘림

가로 15.7%는 적지 않다. 인물이 가운데 있지 않으면 팔이나 어깨가 잘릴
수 있다. OpenAI가 세로로 주는 가장 큰 값이라 피할 방법이 없으므로
숨기지 않고 적어 둔다.

확인하지 못한 것
----------------
OPENAI_API_KEY가 없어 실제 왕복을 확인하지 못했다. 주소·모델·크기는
여기 적힌 것이 실제와 다를 수 있으므로 환경변수로 바꿀 수 있게 둔다.
바뀌더라도 코드를 고칠 필요가 없어야 한다.

    OPENAI_API_KEY   필수
    OPENAI_API_URL   기본 https://api.openai.com
    GPT_IMAGE_MODEL  기본 gpt-image-1
    GPT_IMAGE_SIZE   기본 1024x1536
    GPT_IMAGE_QUALITY 기본 high

후처리는 현재 엔진과 같은 것을 쓴다
-----------------------------------
image_service.enhance_image는 생성한 이미지마다 걸리는 처리다. 여기만
건너뛰면 같은 프로젝트 안에서 그림의 성격이 갈린다.
"""

import base64
import os

import requests

from app.services.image_service import enhance_image

DEFAULT_API_URL = "https://api.openai.com"
DEFAULT_MODEL = "gpt-image-1"

API_KEY_SETTING = "OPENAI_API_KEY"

# 세로 영상이다. OpenAI가 주는 것 중 가장 세로로 긴 값이다.
DEFAULT_SIZE = "1024x1536"

DEFAULT_QUALITY = "high"

# 한 번에 끝나지만 그 한 번이 길다. 짧게 잡으면 다 만들어진 이미지를
# 버리게 된다.
REQUEST_TIMEOUT_SECONDS = 180
DOWNLOAD_TIMEOUT_SECONDS = 60

# 프롬프트가 안전 기준에 걸린 것. 키가 틀린 것과 전혀 다른 일이고,
# 사람이 할 일도 다르다.
MODERATION_BLOCKED = "moderation_blocked"


class GptImageUnavailable(RuntimeError):
    """GPT Image를 쓸 수 없다.

    설정이 없거나 API가 거절했다. 무엇이 왜 안 되는지 적는다 - 사람이
    고쳐서 다시 할 수 있어야 한다."""


def api_url() -> str:
    return (os.getenv("OPENAI_API_URL") or DEFAULT_API_URL).rstrip("/")


def model_id() -> str:
    return os.getenv("GPT_IMAGE_MODEL") or DEFAULT_MODEL


def image_size() -> str:
    """OpenAI가 받는 값 중 하나여야 한다. 아니면 API가 거절한다."""

    return os.getenv("GPT_IMAGE_SIZE") or DEFAULT_SIZE


def _quality() -> str:
    return os.getenv("GPT_IMAGE_QUALITY") or DEFAULT_QUALITY


def _api_key() -> str:
    key = os.getenv(API_KEY_SETTING)

    if not key:
        raise GptImageUnavailable(
            f"{API_KEY_SETTING}가 설정되지 않았습니다. "
            "GPT Image로 만들려면 그 값이 필요합니다."
        )

    return key


def _refused(response) -> GptImageUnavailable:
    """
    왜 거절당했는지 사람이 읽을 수 있게 만든다.

    프롬프트가 막힌 것은 따로 말한다 - 키를 고쳐도 소용없고 프롬프트를
    고쳐야 하는 일이라, 같은 문장으로 뭉뚱그리면 엉뚱한 곳을 보게 된다.
    """

    try:
        error = (response.json() or {}).get("error") or {}
    except ValueError:
        error = {}

    detail = error.get("message") or response.text

    if error.get("code") == MODERATION_BLOCKED:
        return GptImageUnavailable(
            f"GPT Image가 프롬프트를 거절했습니다: {detail} "
            "프롬프트를 바꾸거나 다른 Provider를 고르십시오."
        )

    return GptImageUnavailable(
        f"GPT Image가 요청을 거절했습니다 ({response.status_code}): {detail}"
    )


def _ask(prompt: str, key: str) -> dict:
    response = requests.post(
        f"{api_url()}/v1/images/generations",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_id(),
            "prompt": prompt,
            "n": 1,
            "size": image_size(),
            "quality": _quality(),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise _refused(response)

    return response.json() or {}


def _image_bytes(payload: dict) -> bytes:
    """
    응답에서 이미지를 꺼낸다.

    gpt-image-1은 base64로 담아 보낸다. 모델을 바꾸면 주소로 오는
    것도 있어서 둘 다 받는다.
    """

    entries = payload.get("data") or []

    if not entries:
        raise GptImageUnavailable(
            "GPT Image가 이미지를 돌려주지 않았습니다."
        )

    entry = entries[0] or {}

    encoded = entry.get("b64_json")

    if encoded:
        try:
            return base64.b64decode(encoded)
        except (ValueError, TypeError) as exc:
            raise GptImageUnavailable(
                f"GPT Image가 보낸 이미지를 읽지 못했습니다: {exc}"
            ) from exc

    link = entry.get("url")

    if not link:
        raise GptImageUnavailable(
            "GPT Image의 답에 이미지도 주소도 없습니다."
        )

    response = requests.get(link, timeout=DOWNLOAD_TIMEOUT_SECONDS)

    if response.status_code != 200:
        raise GptImageUnavailable(
            f"GPT Image 이미지를 내려받지 못했습니다 "
            f"({response.status_code})."
        )

    return response.content


def generate_image(prompt: str, output_file: str) -> str:
    """
    이미지 한 장을 만들어 output_file에 쓴다.

    실패하면 파일을 남기지 않는다 - 반쯤 만들어진 것이 남으면 뒤
    단계가 그것을 완성된 것으로 읽는다. 그래서 바이트를 모두 손에
    넣은 뒤에야 파일을 연다.
    """

    key = _api_key()

    image = _image_bytes(_ask(prompt, key))

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as f:
        f.write(image)

    # 현재 엔진이 생성한 이미지마다 거치는 처리. 여기만 건너뛰면
    # 같은 프로젝트 안에서 그림의 성격이 갈린다.
    enhance_image(output_file)

    print(f"Saved : {output_file} (GPT Image {model_id()})")

    return output_file
