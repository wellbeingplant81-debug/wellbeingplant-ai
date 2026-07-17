import os

import requests

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
VOICES_URL = "https://api.elevenlabs.io/v1/voices"

DEFAULT_MODEL_ID = "eleven_multilingual_v2"
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
    voice_name = os.getenv("ELEVENLABS_VOICE_NAME")

    # Sprint123 - Production Policy: 실제 TTS 호출마다 Provider/Voice
    # Name/Voice ID를 로그로 남긴다 - Longform이 정말 ElevenLabs를
    # 쓰는지(Google로 조용히 새지 않았는지) 실행 로그만 보고도 확인할
    # 수 있어야 한다.
    print(
        f"[TTS] Provider=ElevenLabs "
        f"Voice Name={voice_name or '(ELEVENLABS_VOICE_ID 직접 지정)'} "
        f"Voice ID={voice_id}"
    )

    response = requests.post(
        ELEVENLABS_API_URL.format(voice_id=voice_id),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": DEFAULT_MODEL_ID,
        },
        timeout=TTS_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"ElevenLabs API 호출 실패 ({response.status_code}): {response.text}"
        )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as f:
        f.write(response.content)

    return output_file


def list_voices():

    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        raise Exception("ELEVENLABS_API_KEY 환경변수가 설정되어 있지 않습니다.")

    response = requests.get(
        VOICES_URL,
        headers={"xi-api-key": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"ElevenLabs Voice 목록 조회 실패 ({response.status_code}): {response.text}"
        )

    return [voice["name"] for voice in response.json().get("voices", [])]


def validate_availability() -> tuple:
    """
    Sprint123 - Longform Pre-flight Validation. Production(Script/Image/
    Asset/Video 생성)을 시작하기 전에 ElevenLabs를 실제로 쓸 수 있는지
    확인한다. 아래 중 하나라도 실패하면 예외를 던진다 - 절대 다른
    provider로 조용히 대체하지 않는다(generate_voice()/_resolve_voice_id
    와 동일한 원칙):

    1. ELEVENLABS_API_KEY 환경변수 존재
    2. ELEVENLABS_VOICE_ID 또는 ELEVENLABS_VOICE_NAME 중 하나 존재
    3. Voice 목록 API가 실제로 응답한다(키 유효성 + 연결 가능 여부를
       함께 검증 - _resolve_voice_id()는 ELEVENLABS_VOICE_ID가 직접
       설정된 경로에서는 네트워크 호출을 하지 않으므로, 여기서는 두
       경로 모두 항상 실제 API를 호출해 계정에 그 Voice가 실재하는지
       확인한다)
    4. 지정된 Voice(이름 또는 ID)가 그 목록에 실제로 존재

    성공하면 (voice_id, voice_name) 튜플을 반환한다 - 호출자가 로그에
    남길 수 있도록. voice_name은 ELEVENLABS_VOICE_ID로 직접 지정한
    경우 None이다. 여기서 확인한 voice_id는 _resolve_voice_id_by_name()
    과 동일한 캐시에 채워두어, 이어지는 실제 generate_voice() 호출이
    같은 이름을 다시 조회하지 않게 한다.
    """

    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        raise Exception("ELEVENLABS_API_KEY 환경변수가 설정되어 있지 않습니다.")

    voice_name = os.getenv("ELEVENLABS_VOICE_NAME")
    voice_id_env = os.getenv("ELEVENLABS_VOICE_ID")

    if not voice_name and not voice_id_env:
        raise Exception(
            "ELEVENLABS_VOICE_ID 또는 ELEVENLABS_VOICE_NAME 환경변수가 "
            "설정되어 있지 않습니다."
        )

    response = requests.get(
        VOICES_URL,
        headers={"xi-api-key": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise Exception(
            f"ElevenLabs Voice 목록 조회 실패 ({response.status_code}): {response.text}"
        )

    voices = response.json().get("voices", [])

    if voice_name:
        cache_key = voice_name.strip().lower()
        matched = next(
            (v for v in voices if v.get("name", "").strip().lower() == cache_key),
            None,
        )
        if matched is None:
            raise Exception(
                f"ElevenLabs Voice '{voice_name}'을(를) 찾을 수 없습니다 - "
                f"다른 voice로 자동 대체하지 않고 에러로 처리합니다."
            )
        voice_id = matched["voice_id"]
        _voice_id_cache[cache_key] = voice_id
        return voice_id, voice_name

    matched = next((v for v in voices if v.get("voice_id") == voice_id_env), None)
    if matched is None:
        raise Exception(
            f"ElevenLabs Voice ID '{voice_id_env}'을(를) 계정에서 찾을 수 "
            f"없습니다."
        )

    return voice_id_env, None
