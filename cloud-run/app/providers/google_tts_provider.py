import os

from google.cloud import texttospeech

from app.services import audio_policy, voice_policy


PROVIDER_NAME = "google"


def generate_voice(text: str, output_file: str):

    # Sprint244 - 돈이 나가기 직전의 마지막 문.
    #
    # 고르지 않은 사람이 여기까지 오고 있었다. .env 의 TTS_PROVIDER
    # 한 줄이 기본값으로 이 경로를 정했고, 화면에는 그런 선택이
    # 없었다.
    #
    # 관문이 tts_provider 가 아니라 여기 있는 이유는 그 위층을 무료인
    # 내 PC 음성도 지나기 때문이다. 목이 아니라 문에 세운다.
    voice_policy.require_allowed(output_file, PROVIDER_NAME)

    client = texttospeech.TextToSpeechClient()

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        name="ko-KR-Chirp3-HD-Aoede",
    )

    # Sprint63 - Master Quality Audio. AudioEncoding.MP3로 받으면 24kHz
    # mono 32kbps로 내려와서 99.9% rolloff가 5,848Hz에서 잘린다(실측).
    # LINEAR16은 무손실 PCM이라 9,152Hz까지 그대로 살아 있다. 이 파일이
    # 파이프라인 전체의 유일한 오디오 원본이므로, 여기서 잃은 대역은
    # 이후 어떤 단계에서도 복구되지 않는다.
    #
    # sample_rate_hertz는 정책값(= Chirp3-HD 네이티브 24kHz)으로 고정한다
    # - 더 높게 요청해도 서버가 업샘플링만 해 줄 뿐 대역은 늘지 않는다.
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=audio_policy.NARRATION_SAMPLE_RATE_HZ,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as out:
        out.write(response.audio_content)

    return output_file
