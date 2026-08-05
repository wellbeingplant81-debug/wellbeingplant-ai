import os

from google.cloud import texttospeech

from app.services import audio_policy


def generate_voice(text: str, output_file: str):

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
