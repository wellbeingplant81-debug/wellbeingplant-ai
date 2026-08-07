"""
Sprint134 - 모델을 직접 부르는 대본 Provider들을 등록소에 올린다
(Epic 56, Phase 11).

Sprint133이 Gemini 하나를 위해 만든 gemini_script.py를 여기로 합쳤다.
Claude가 오면서 같은 클래스가 두 벌이 될 참이었고, 세 번째부터 조금씩
갈라진다 - generated_image.py가 이미 표 하나로 정리한 그 문제다.

실제 호출은 엔진 층(app/providers/*_script_provider.py)에 있다. 여기는
화면이 목록을 그리는 자리이고, 부르면 그 모듈로 간다 - 두 자리가 다른
곳을 부르면 화면이 말하는 것과 실제로 도는 것이 갈린다.

층을 나누는 이유는 엔진 층이 app.production을 import하면 안 되기
때문이다(test_production_architecture가 강제한다).

current와 무엇이 다른가
-----------------------
current는 이 저장소의 파이프라인 전체다 - 바이럴 Writer, 인물 일관성
규칙, 43~47초 재생성 루프, 주제 이탈 재시도. 이것들은 모델을 한 번
부른다. 그 사실을 description에 적어 화면이 그대로 보여 준다.

엔진 모듈을 import하지 않는다
-----------------------------
import하면 google.genai 같은 무거운 것이 딸려 와서, 목록을 그리는
것만으로 수백 개 모듈이 켜진다(test_registering_pulls_in_no_heavy_module이
잰다). 그래서 키 이름은 아래 표에 적어 두고, 값이 어긋나지 않도록
테스트가 잠근다.
"""

import importlib
import os

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    ProviderUnavailable,
    StageProvider,
    StageProviderError,
)

_BYPASSES = (
    "현재 엔진의 바이럴 Writer·인물 일관성 규칙·Duration Gate 재생성·"
    "주제 이탈 재시도를 거치지 않고 한 번만 부릅니다."
)


class GeneratedScriptProvider(StageProvider):
    """모델을 직접 부르는 대본 Provider. 등록소에 올라가는 쪽."""

    # Sprint124의 자리들과 구분하는 표시. 코드가 있다는 뜻이다.
    coming_soon = False

    def __init__(self, name, display_name, vendor, key_setting, module_path,
                 description=""):
        self._key_setting = key_setting
        self._module_path = module_path

        self.capabilities = ProviderCapabilities(
            name=name,
            stage=stages.SCRIPT,
            # 현재 엔진과 나란히 재 본 적이 없다. 등급을 매길 근거가
            # 생기면 그때 바꾼다.
            quality_tier=STANDARD,
            supported_source_modes=(source_modes.GENERATE,),
            required_settings=(key_setting,),
            description=description,
            display_name=display_name,
            vendor=vendor,
            # 실측 금액 계산은 아직이다. 모르는 것은 비워 둔다.
            estimated_cost=None,
            supports_streaming=False,
        )

    # ---- 쓸 수 있는가 -------------------------------------------------

    def availability(self):
        """(쓸 수 있는가, 왜 못 쓰는가). 화면이 그대로 보여 준다.

        엔진 모듈을 켜지 않고 답한다 - 목록을 그리는 것만으로 모델
        라이브러리를 끌고 올 이유가 없다."""

        if os.getenv(self._key_setting):
            return True, ""

        return False, f"{self._key_setting}가 설정되지 않았습니다."

    def is_configured(self) -> bool:
        return self.availability()[0]

    # ---- 만든다 -------------------------------------------------------

    def generate(self, request):
        self._require(source_modes.GENERATE)

        available, reason = self.availability()

        if not available:
            raise ProviderUnavailable(reason)

        if request is None:
            raise ValueError("이 단계에 필요한 값이 없습니다: ['topic']")

        request.require("topic")

        # 늦게 부른다. 여기서야 실제로 만들 것이므로 무거워도 된다.
        from app.providers import direct_script

        module = importlib.import_module(self._module_path)

        try:
            return module.generate_script(request.topic)
        except direct_script.ScriptProviderUnavailable as exc:
            # 설정 문제는 등록소의 말로 바꾼다 - 화면이 이 뜻으로 읽는다.
            raise ProviderUnavailable(str(exc)) from exc
        except direct_script.ScriptProviderError as exc:
            raise StageProviderError(str(exc)) from exc


# 이름 · 화면에 뜨는 이름 · 만든 곳 · 필요한 키 · 실제로 부르는 모듈.
#
# 모듈 경로는 다리(step01_script.DIRECT_SCRIPT_PROVIDERS)가 쓰는 것과
# 같아야 한다. 갈라지면 화면이 말하는 것과 실제로 도는 것이 달라진다.
GENERATED_SCRIPT_PROVIDERS = (
    ("gemini", "Gemini", "Google", "GOOGLE_API_KEY",
     "app.providers.gemini_script_provider",
     "Gemini를 직접 불러 대본을 만듭니다. 현재 엔진과 같은 모델이지만 "
     + _BYPASSES),
    ("claude", "Claude", "Anthropic", "ANTHROPIC_API_KEY",
     "app.providers.claude_script_provider",
     "Claude를 직접 불러 대본을 만듭니다. " + _BYPASSES),
    ("openai", "OpenAI", "OpenAI", "OPENAI_API_KEY",
     "app.providers.openai_script_provider",
     "OpenAI를 직접 불러 대본을 만듭니다. 이미지의 GPT Image와 같은 "
     "키를 씁니다. " + _BYPASSES),
)


def generated_script_providers():
    """등록할 것들을 만들어 돌려준다. 여기서 등록하지 않는다 -
    등록은 bootstrap이 명시적으로 부를 때만 일어난다(Sprint103)."""

    return [GeneratedScriptProvider(*entry)
            for entry in GENERATED_SCRIPT_PROVIDERS]
