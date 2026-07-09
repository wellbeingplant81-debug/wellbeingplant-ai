import os

from app.providers import elevenlabs_provider
from app.providers import google_tts_provider
from app.services.speech_normalizer import normalize_for_speech
from app.services.voice_quality_engine import optimize_for_tts


def generate_voice(text: str, output_file: str):

    provider = os.getenv("TTS_PROVIDER", "google").lower()

    print(f"Using TTS Provider: {'ElevenLabs' if provider == 'elevenlabs' else 'Google'}")

    if provider == "elevenlabs":
        # optimize_for_tts()는 <break time="Xs" /> 마크업을 text에
        # 직접 삽입한다 - ElevenLabs만 이 마크업을 해석하므로
        # (voice_quality_engine.py 참고) Google TTS 경로에는 절대
        # 적용하지 않는다. 자막(subtitle_service.py)은 이 최적화된
        # 텍스트가 아니라 원본 scene["narration"]과 실제 mp3 길이를
        # 그대로 사용하므로 자막 sync에는 영향이 없다.
        optimized_text = optimize_for_tts(text)
        return elevenlabs_provider.generate_voice(optimized_text, output_file)

    # Sprint52 - Speech Normalization Engine: "2번" 같은 표기를 실제
    # 발음("두 번")으로 바꿔 Google TTS에만 전달한다. 자막/narration
    # 원문은 절대 바꾸지 않는다 - optimize_for_tts()와 동일한 원칙.
    normalized_text = normalize_for_speech(text)
    return google_tts_provider.generate_voice(normalized_text, output_file)


def list_voices():

    provider = os.getenv("TTS_PROVIDER", "google").lower()

    if provider == "elevenlabs":
        return elevenlabs_provider.list_voices()

    return google_tts_provider.list_voices()