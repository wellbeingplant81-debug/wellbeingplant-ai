import os

from app.providers import elevenlabs_provider
from app.providers import google_tts_provider
from app.services.speech_normalizer import normalize_for_speech
from app.services.voice_quality_engine import optimize_for_tts


# Sprint126 - 이 경로가 아는 이름. 화면이 프로젝트에 적을 수 있는
# 값이기도 하므로 여기서 소유한다.
#
# app.production 등록소의 이름과는 다른 층이다. 거기 있는 "google_tts"는
# 파이프라인을 거치지 않고 모델을 직접 부르는 자리(아직 비어 있음)이고,
# 여기 "google"은 지금 엔진이 실제로 쓰는 그 경로다.
#
# Sprint151 - local_voice가 셋째다. 앞의 둘과 성질이 다르다: 모델을
# 부르지 않고 사람이 녹음해 둔 파일을 고른다. 그래서 아래에서 글을
# 다듬는 단계를 거치지 않는다 - 다듬을 대상이 없다.
PROVIDERS = ("google", "elevenlabs", "local_voice")

LOCAL_VOICE = "local_voice"


def generate_voice(text: str, output_file: str, provider: str = None):
    """
    Sprint125 - 어느 Provider를 쓸지 인자로도 받는다.

    주지 않으면 예전 그대로 TTS_PROVIDER를 읽는다 - 기존 호출자
    (scene_tts_service, studio_review)는 한 글자도 바뀌지 않는다.

    인자를 더한 이유는 StageProvider가 환경변수를 잠깐 바꿔 쓰면 안
    되기 때문이다. studio_jobs는 파이프라인을 스레드로 돌리므로 두
    작업이 겹치면 서로의 설정을 덮어쓴다.
    """

    provider = (provider or os.getenv("TTS_PROVIDER", "google")).lower()

    # Sprint151 - 내 PC 음성. 아래 두 갈래보다 먼저 본다.
    #
    # 여기서 늦게 import한다 - 이 모듈은 파이프라인이 언제나 켜는
    # 자리라, 고르지 않은 사람에게까지 남의 Provider를 지우지 않는다.
    #
    # 글을 다듬지 않고 넘긴다. normalize_for_speech도 optimize_for_tts도
    # 부르지 않는다 - 둘 다 "이 글을 어떻게 읽어 줄까"를 모델에게 말하는
    # 것이고, 이미 녹음된 파일에는 말할 상대가 없다.
    if provider == LOCAL_VOICE:
        from app.providers import local_voice_provider

        print("Using TTS Provider: 내 PC 음성 (API 호출 없음)")

        return local_voice_provider.generate_voice(text, output_file)

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