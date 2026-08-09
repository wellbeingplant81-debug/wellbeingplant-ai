import os
import subprocess
import tempfile

import requests

from app.services import audio_policy, media_tools

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
VOICES_URL = "https://api.elevenlabs.io/v1/voices"

DEFAULT_MODEL_ID = "eleven_multilingual_v2"


def model_id() -> str:
    """Sprint125 - ELEVENLABS_MODEL로 바꿀 수 있다. 없으면 기본값."""

    return os.getenv("ELEVENLABS_MODEL") or DEFAULT_MODEL_ID
REQUEST_TIMEOUT_SECONDS = 10
TTS_TIMEOUT_SECONDS = 30

_voice_id_cache = {}


def _resolve_voice_id_by_name(name: str, api_key: str) -> str:
    """
    ElevenLabs 계정의 Voice 목록에서 이름이 정확히 일치(대소문자 무시)
    하는 voice_id를 조회합니다. 파이프라인 한 번 실행 중 여러 scene이
    동일한 이름을 반복 조회하지 않도록 프로세스 내에서 캐시합니다.

    찾지 못하거나 목록 조회 자체가 실패하면 예외를 발생시키며, 절대
    다른 voice로 자동 대체하지 않습니다.
    """

    cache_key = name.strip().lower()

    if cache_key in _voice_id_cache:
        return _voice_id_cache[cache_key]

    response = requests.get(
        VOICES_URL,
        headers={"xi-api-key": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"ElevenLabs Voice 목록 조회 실패 ({response.status_code}): {response.text}"
        )

    for voice in response.json().get("voices", []):
        if voice.get("name", "").strip().lower() == cache_key:
            voice_id = voice["voice_id"]
            _voice_id_cache[cache_key] = voice_id
            return voice_id

    raise Exception(
        f"ElevenLabs Voice '{name}'을(를) 찾을 수 없습니다 - "
        f"다른 voice로 자동 대체하지 않고 에러로 처리합니다."
    )


def _resolve_voice_id(api_key: str) -> str:
    """
    ELEVENLABS_VOICE_NAME이 설정되어 있으면 이름 기반으로 조회한
    voice_id를 사용합니다 (예: "Brandon"). 설정되어 있지 않으면 기존
    ELEVENLABS_VOICE_ID를 그대로 사용합니다. 둘 다 없으면 예외를
    발생시킵니다 - 어떤 경우에도 다른 voice로 조용히 대체하지
    않습니다.
    """

    voice_name = os.getenv("ELEVENLABS_VOICE_NAME")

    if voice_name:
        return _resolve_voice_id_by_name(voice_name, api_key)

    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    if not voice_id:
        raise Exception(
            "ELEVENLABS_VOICE_ID 또는 ELEVENLABS_VOICE_NAME 환경변수가 "
            "설정되어 있지 않습니다."
        )

    return voice_id


def generate_voice(text: str, output_file: str):

    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        raise Exception("ELEVENLABS_API_KEY 환경변수가 설정되어 있지 않습니다.")

    voice_id = _resolve_voice_id(api_key)

    response = requests.post(
        ELEVENLABS_API_URL.format(voice_id=voice_id),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": model_id(),
        },
        timeout=TTS_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"ElevenLabs API 호출 실패 ({response.status_code}): {response.text}"
        )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    _write_policy_audio(response.content, output_file)

    return output_file


def _write_policy_audio(audio_bytes: bytes, output_file: str):
    """
    Sprint63 - Master Quality Audio. ElevenLabs는 기본적으로 MP3를
    돌려주지만, 파이프라인의 나머지 구간은 무손실 PCM WAV만 다룬다
    (app/services/audio_policy.py). 받은 바이트를 그대로 .wav 이름으로
    저장하면 컨테이너와 내용이 어긋나므로, 여기서 한 번만 디코딩해
    정책 포맷으로 정규화한다.

    ElevenLabs가 이미 만든 MP3 손실은 되돌릴 수 없다 - 여기서 막는 것은
    "그 뒤로 더 쌓이는" 재인코딩이다. Google TTS 경로(LINEAR16)는 애초에
    손실이 없으므로 이런 변환 자체가 필요 없다.
    """

    with tempfile.NamedTemporaryFile(
        suffix=".src", delete=False,
    ) as tmp:
        tmp.write(audio_bytes)
        source_path = tmp.name

    try:
        result = subprocess.run(
            [media_tools.resolve(media_tools.FFMPEG),
             "-y", "-i", source_path]
            + audio_policy.pcm_output_args()
            + [output_file],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            raise Exception(
                f"ElevenLabs 오디오를 정책 포맷으로 변환하지 못했습니다: "
                f"{result.stderr}"
            )
    finally:
        os.remove(source_path)
