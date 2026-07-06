import os

from app.providers import elevenlabs_provider
from app.providers import google_tts_provider
from app.services.voice_quality_engine import optimize_for_tts


def generate_voice(text: str, output_file: str):

    provider = os.getenv("TTS_PROVIDER", "google").lower()

    if provider == "elevenlabs":
        # optimize_for_tts()는 <break time="Xs" /> 마크업을 text에
        # 직접 삽입한다 - ElevenLabs만 이 마크업을 해석하므로
        # (voice_quality_engine.py 참고) Google TTS 경로에는 절대
        # 적용하지 않는다. 자막(subtitle_service.py)은 이 최적화된
        # 텍스트가 아니라 원본 scene["narration"]과 실제 mp3 길이를
        # 그대로 사용하므로 자막 sync에는 영향이 없다.
        optimized_text = optimize_for_tts(text)
        return elevenlabs_provider.generate_voice(optimized_text, output_file)

    return google_tts_provider.generate_voice(text, output_file)