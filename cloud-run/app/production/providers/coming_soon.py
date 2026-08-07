"""
Sprint124 - 아직 붙지 않은 Provider들 (Epic 56, Phase 1).

자리를 만든다. 실제 API는 하나도 부르지 않는다.

붙지 않았다는 것을 코드와 화면이 똑같이 말해야 한다. generate()는
ProviderUnavailable을 던지고, 화면은 Coming Soon으로 그린다. 되는
척하는 자리는 하나도 없다.

지어내지 않는 것 둘
-------------------
비용. estimated_cost는 전부 None이다. 우리는 이들의 단가를 모른다.
Sprint117부터 이 저장소는 모르면 "단가 미상"으로 적어 왔고, Sprint119에서
금액을 목표로만 쓰다가 Sprint120에서 아예 걷어냈다. 숫자를 채우는 것은
실제 단가를 받은 뒤의 일이다.

품질. quality_tier는 재 본 것에만 의미가 있다. 부르지도 않은 것을
★★★★★로 매기는 것은 지어내는 일이라 전부 STANDARD로 둔다 - 등급을
매길 근거가 아직 없다는 뜻이고, 화면은 별 대신 "미측정"을 적는다.

Sprint125 - ElevenLabs는 여기서 빠졌다. 엔진이 이미 있어서 실제
Provider(elevenlabs_voice.py)로 올라갔다.

겹치는 이름에 대해
------------------
현재 엔진은 이미 gemini-2.5-pro / imagen-4.0-generate-001 /
ko-KR-Chirp3-HD-Aoede를 쓴다. 그런데도 Gemini·Imagen·Google TTS를
따로 두는 이유가 있다.

    current   이 저장소의 파이프라인을 거친다 - Duration Gate,
              Viral Writer, 품질 게이트, 재생성 정책이 붙어 있다
    이것들    모델을 직접 부르는 자리다 - 아직 비어 있다

같은 모델이라도 거치는 것이 다르므로 결과가 같지 않다. 그 사실을
description에 적어 두어 화면이 그대로 보여 준다.
"""

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    ProviderUnavailable,
    StageProvider,
)


class ComingSoonProvider(StageProvider):
    """자리만 있는 Provider. 부르면 정직하게 거절한다."""

    # 화면이 "고를 수는 있어도 아직 못 쓴다"를 판단하는 표시.
    coming_soon = True

    def __init__(self, name, stage, display_name, vendor, required_settings,
                 description=""):
        self.capabilities = ProviderCapabilities(
            name=name,
            stage=stage,
            quality_tier=STANDARD,
            supported_source_modes=(source_modes.GENERATE,),
            required_settings=tuple(required_settings),
            description=description,
            display_name=display_name,
            vendor=vendor,
            # 모르는 것은 비워 둔다.
            estimated_cost=None,
            supports_streaming=False,
        )

    def generate(self, request):
        raise ProviderUnavailable(
            f"{self.capabilities.label}은(는) 아직 붙지 않았습니다. "
            f"필요한 것: {', '.join(self.capabilities.required_settings)}."
        )


# 같은 모델을 현재 엔진이 이미 쓰고 있는 경우 그 사실을 적는다.
_ALREADY = (
    "현재 엔진이 이미 {model}을(를) 씁니다. 이 자리는 파이프라인을 "
    "거치지 않고 모델을 직접 부르는 쪽이고, 아직 비어 있습니다."
)

COMING_SOON = (
    # --- 대본 ---
    ("gemini", stages.SCRIPT, "Gemini", "Google",
     ("GOOGLE_API_KEY",), _ALREADY.format(model="gemini-2.5-pro")),
    ("claude", stages.SCRIPT, "Claude", "Anthropic",
     ("ANTHROPIC_API_KEY",), ""),
    ("openai", stages.SCRIPT, "OpenAI", "OpenAI",
     ("OPENAI_API_KEY",), ""),
    ("deepseek", stages.SCRIPT, "DeepSeek", "DeepSeek",
     ("DEEPSEEK_API_KEY",), ""),

    # --- 이미지 ---
    ("imagen", stages.IMAGE, "Imagen", "Google",
     ("GOOGLE_API_KEY",), _ALREADY.format(model="imagen-4.0-generate-001")),
    # Sprint130 FLUX, Sprint131 GPT Image는 실제로 붙었다. Sprint132에
    # 여기서 빼고 generated_image.py로 옮겼다 - 같은 이름을 두 곳에서
    # 등록하면 나중 것이 앞의 것을 가린다.
    ("ideogram", stages.IMAGE, "Ideogram", "Ideogram",
     ("IDEOGRAM_API_KEY",), ""),

    # --- 음성 ---
    ("google_tts", stages.VOICE, "Google TTS", "Google",
     ("GOOGLE_APPLICATION_CREDENTIALS",),
     _ALREADY.format(model="ko-KR-Chirp3-HD-Aoede")),
    ("openai_voice", stages.VOICE, "OpenAI Voice", "OpenAI",
     ("OPENAI_API_KEY",), ""),
)


def coming_soon_providers():
    """등록할 것들을 만들어 돌려준다. 여기서 등록하지 않는다 -
    등록은 bootstrap이 명시적으로 부를 때만 일어난다(Sprint103)."""

    return [ComingSoonProvider(*entry) for entry in COMING_SOON]
