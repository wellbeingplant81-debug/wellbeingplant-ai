import os

import requests

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

DEFAULT_MODEL_ID = "eleven_multilingual_v2"


def generate_voice(text: str, output_file: str):

    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    if not api_key:
        raise Exception("ELEVENLABS_API_KEY 환경변수가 설정되어 있지 않습니다.")

    if not voice_id:
        raise Exception("ELEVENLABS_VOICE_ID 환경변수가 설정되어 있지 않습니다.")

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
    )

    if response.status_code != 200:
        raise Exception(
            f"ElevenLabs API 호출 실패 ({response.status_code}): {response.text}"
        )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as f:
        f.write(response.content)

    return output_file
