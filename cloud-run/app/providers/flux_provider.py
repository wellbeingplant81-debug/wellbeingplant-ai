"""
Sprint130 - FLUX로 이미지 한 장을 만든다 (Epic 56, Phase 7).

Sprint127이 놓은 다리에 처음으로 도착하는 실제 Provider다. 그전까지
image_provider는 이름만 날랐고 도착지에서 전부 거절했다.

current를 대체하지 않는다. current는 Best-of-N · 품질 게이트 ·
Pexels 폴백 · 재시도까지 붙은 엔진 전체이고, 이 파일은 이미지 한 장을
만드는 것뿐이다.

FLUX는 비동기다
---------------
요청하면 작업 id를 돌려주고, 준비되면 결과 주소가 나온다. 그래서
세 걸음이다.

    제출     POST {base}/v1/{model}
    기다림   GET  {base}/v1/get_result?id=...   (Ready가 될 때까지)
    받기     GET  {sample url}                  -> 이미지 바이트

영원히 기다리지 않는다. MAX_POLLS를 넘기면 실패로 본다 - 파이프라인
한가운데서 멈춰 있는 것보다 실패가 낫다.

확인하지 못한 것
----------------
FLUX API 키가 없어 실제 왕복을 확인하지 못했다. 주소와 모델 이름은
여기 적힌 것이 실제와 다를 수 있으므로 환경변수로 바꿀 수 있게 둔다.
바뀌더라도 코드를 고칠 필요가 없어야 한다.

    FLUX_API_KEY   필수
    FLUX_API_URL   기본 https://api.bfl.ml
    FLUX_MODEL     기본 flux-pro-1.1

후처리는 현재 엔진과 같은 것을 쓴다
-----------------------------------
image_service.enhance_image는 생성한 이미지마다 걸리는 처리다. FLUX
결과만 건너뛰면 같은 프로젝트 안에서 그림의 성격이 갈린다.
"""

import os
import time

import requests

from app.services.image_service import enhance_image

DEFAULT_API_URL = "https://api.bfl.ml"
DEFAULT_MODEL = "flux-pro-1.1"

API_KEY_SETTING = "FLUX_API_KEY"

# 세로 영상이다. 파이프라인 전체가 9:16을 쓴다(최종 MP4는 1080x1920).
#
# 576x1024는 정확히 9:16이고 둘 다 32의 배수다 - 확산 모델이 대개
# 요구하는 조건이다. 흔히 쓰이는 768x1344는 4:7이라 여기서는 맞지
# 않는다(영상에 넣으면 잘리거나 늘어난다).
#
# 더 큰 값을 쓸 수 있는지는 실제 API 제한을 확인해야 알 수 있으므로
# 환경변수로 바꿀 수 있게 둔다.
DEFAULT_WIDTH = 576
DEFAULT_HEIGHT = 1024

SUBMIT_TIMEOUT_SECONDS = 30
POLL_TIMEOUT_SECONDS = 30
DOWNLOAD_TIMEOUT_SECONDS = 60

POLL_INTERVAL_SECONDS = 1.0
MAX_POLLS = 60

READY = "Ready"


class FluxUnavailable(RuntimeError):
    """FLUX를 쓸 수 없다.

    설정이 없거나 API가 거절했다. 무엇이 왜 안 되는지 적는다 - 사람이
    고쳐서 다시 할 수 있어야 한다."""


def api_url() -> str:
    return (os.getenv("FLUX_API_URL") or DEFAULT_API_URL).rstrip("/")


def model_id() -> str:
    return os.getenv("FLUX_MODEL") or DEFAULT_MODEL


def _api_key() -> str:
    key = os.getenv(API_KEY_SETTING)

    if not key:
        raise FluxUnavailable(
            f"{API_KEY_SETTING}가 설정되지 않았습니다. "
            "FLUX로 만들려면 그 값이 필요합니다."
        )

    return key


def _size():
    """(가로, 세로). 환경변수로 바꿀 수 있다."""

    def _read(name, default):
        try:
            return int(os.getenv(name) or default)
        except ValueError:
            return default

    return _read("FLUX_WIDTH", DEFAULT_WIDTH), _read("FLUX_HEIGHT",
                                                     DEFAULT_HEIGHT)


def _submit(prompt: str, key: str) -> str:
    width, height = _size()

    response = requests.post(
        f"{api_url()}/v1/{model_id()}",
        headers={"x-key": key, "Content-Type": "application/json"},
        json={
            "prompt": prompt,
            "width": width,
            "height": height,
            "output_format": "png",
        },
        timeout=SUBMIT_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise FluxUnavailable(
            f"FLUX가 요청을 거절했습니다 ({response.status_code}): "
            f"{response.text}"
        )

    job_id = (response.json() or {}).get("id")

    if not job_id:
        raise FluxUnavailable("FLUX가 작업 번호를 돌려주지 않았습니다.")

    return job_id


def _wait_for_sample(job_id: str, key: str) -> str:
    """준비될 때까지 기다린다. 영원히는 아니다."""

    for _ in range(MAX_POLLS):
        response = requests.get(
            f"{api_url()}/v1/get_result",
            headers={"x-key": key},
            params={"id": job_id},
            timeout=POLL_TIMEOUT_SECONDS,
        )

        if response.status_code != 200:
            raise FluxUnavailable(
                f"FLUX 결과 조회에 실패했습니다 ({response.status_code}): "
                f"{response.text}"
            )

        payload = response.json() or {}

        if payload.get("status") == READY:
            sample = (payload.get("result") or {}).get("sample")

            if not sample:
                raise FluxUnavailable(
                    "FLUX가 준비됐다고 했지만 이미지 주소가 없습니다."
                )

            return sample

        time.sleep(POLL_INTERVAL_SECONDS)

    raise FluxUnavailable(
        f"FLUX가 {MAX_POLLS}번 확인하는 동안 끝나지 않았습니다."
    )


def generate_image(prompt: str, output_file: str) -> str:
    """
    이미지 한 장을 만들어 output_file에 쓴다.

    실패하면 파일을 남기지 않는다 - 반쯤 만들어진 것이 남으면 뒤
    단계가 그것을 완성된 것으로 읽는다.
    """

    key = _api_key()

    sample_url = _wait_for_sample(_submit(prompt, key), key)

    response = requests.get(sample_url, timeout=DOWNLOAD_TIMEOUT_SECONDS)

    if response.status_code != 200:
        raise FluxUnavailable(
            f"FLUX 이미지를 내려받지 못했습니다 ({response.status_code})."
        )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as f:
        f.write(response.content)

    # 현재 엔진이 생성한 이미지마다 거치는 처리. 여기만 건너뛰면
    # 같은 프로젝트 안에서 그림의 성격이 갈린다.
    enhance_image(output_file)

    print(f"Saved : {output_file} (FLUX {model_id()})")

    return output_file
