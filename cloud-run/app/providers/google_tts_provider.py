import os

from google.cloud import texttospeech


def generate_voice(text: str, output_file: str):

    client = texttospeech.TextToSpeechClient()

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        name="ko-KR-Chirp3-HD-Aoede",
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
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
