"""
Sprint133 - Gemini 대본 Provider를 등록소에 올린다 (Epic 56, Phase 10).

실제 호출은 엔진 층(app/providers/gemini_script_provider.py)에 있다.
여기는 화면이 목록을 그리는 자리이고, 부르면 그 모듈로 간다 - 두
자리가 다른 곳을 부르면 화면이 말하는 것과 실제로 도는 것이 갈린다.
Sprint132에서 이미지에 한 것과 같은 구조다.

층을 나누는 이유는 엔진 층이 app.production을 import하면 안 되기
때문이다(test_production_architecture가 강제한다).

current와 무엇이 다른가
-----------------------
같은 gemini-2.5-pro를 부른다. 다른 것은 거치는 것이다 - 이쪽에는
바이럴 템플릿도, 인물 일관성 규칙도, 43~47초 재생성 루프도, 주제
이탈 재시도도 없다. 그 사실을 description에 적어 화면이 그대로
보여 준다.
"""

import os

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    ProviderUnavailable,
    StageProvider,
    StageProviderError,
)

# 엔진이 실제로 읽는 이름. 여기서 새로 정하지 않는다 -
# app/providers/gemini_script_provider.py가 이 이름으로 읽는다.
#
# 그 모듈에서 가져오지 않고 적어 두는 이유가 있다. 그것을 import하면
# google.genai가 딸려 오고, 등록소에 올리는 것만으로 무거운 모듈
# 수백 개가 켜진다(test_registering_pulls_in_no_heavy_module이 잰다).
# 두 값이 어긋나지 않도록 테스트가 잠근다.
API_KEY_SETTING = "GOOGLE_API_KEY"

DESCRIPTION = (
    "Gemini를 직접 불러 대본을 만듭니다. 현재 엔진과 같은 모델이지만 "
    "바이럴 Writer·인물 일관성 규칙·Duration Gate 재생성·주제 이탈 "
    "재시도를 거치지 않고 한 번만 부릅니다."
)


class GeminiScriptProvider(StageProvider):
    """모델을 직접 부르는 대본 Provider. 등록소에 올라가는 쪽."""

    # Sprint124의 자리들과 구분하는 표시. 코드가 있다는 뜻이다.
    coming_soon = False

    def __init__(self):
        self.capabilities = ProviderCapabilities(
            name="gemini",
            stage=stages.SCRIPT,
            # 현재 엔진과 나란히 재 본 적이 없다. 등급을 매길 근거가
            # 생기면 그때 바꾼다.
            quality_tier=STANDARD,
            supported_source_modes=(source_modes.GENERATE,),
            required_settings=(API_KEY_SETTING,),
            description=DESCRIPTION,
            display_name="Gemini",
            vendor="Google",
            # 실측 금액 계산은 아직이다. 모르는 것은 비워 둔다.
            estimated_cost=None,
            supports_streaming=False,
        )

    # ---- 쓸 수 있는가 -------------------------------------------------

    def _engine(self):
        from app.providers import gemini_script_provider

        return gemini_script_provider

    def availability(self):
        """(쓸 수 있는가, 왜 못 쓰는가). 화면이 그대로 보여 준다.

        엔진 모듈을 켜지 않고 답한다 - 목록을 그리는 것만으로
        google.genai를 끌고 올 이유가 없다."""

        if os.getenv(API_KEY_SETTING):
            return True, ""

        return False, f"{API_KEY_SETTING}가 설정되지 않았습니다."

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

        engine = self._engine()

        try:
            return engine.generate_script(request.topic)
        except engine.GeminiScriptUnavailable as exc:
            # 설정 문제는 등록소의 말로 바꾼다 - 화면이 이 뜻으로
            # 읽는다.
            raise ProviderUnavailable(str(exc)) from exc
        except engine.GeminiScriptError as exc:
            raise StageProviderError(str(exc)) from exc
