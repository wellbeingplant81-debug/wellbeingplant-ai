import os

from app.providers import elevenlabs_provider
from app.providers import google_tts_provider


def generate_voice(text: str, output_file: str):

    provider = os.getenv("TTS_PROVIDER", "google").lower()

    if provider == "elevenlabs":
        return elevenlabs_provider.generate_voice(text, output_file)

    return google_tts_provider.generate_voice(text, output_file)