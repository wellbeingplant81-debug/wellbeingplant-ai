"""
Sprint140 - 현재 이미지 엔진이 안에서 쓰는 스톡 검색 자리
(Epic 56, Phase 17).

Sprint138에서 인증을 실제와 맞추면서 하나가 남았다. 이미지의 현재
엔진은 Vertex AI ADC로 Imagen을 부르지만 그것만으로 도는 것이 아니다 -
스톡 검색도 함께 쓰고 그쪽은 다른 키가 필요하다. 담을 자리가 없어
화면이 적지 못했다.

코드에서 확인한 것
------------------
provider_factory.build_provider_chain이 순서를 정한다.

    allow_video=True    pexels_video -> pexels_image
                        -> pixabay_video -> pixabay_image
    allow_video=False   pexels_image -> pixabay_image

두 곳이다 - Pexels와 Pixabay. 각각 동영상과 사진을 찾는다.

"폴백"이라고만 적으면 사실이 아니다
-----------------------------------
asset_integration_service를 보면 순서가 scene마다 다르다.

    visual_type == "real"   스톡을 먼저 본다. 실패하면 Imagen
    visual_type == "ai"     Imagen을 먼저 본다. 실패하면 스톡
    visual_type 없음        스톡을 먼저 본다(품질 게이트가 판단)

셋 중 둘에서 스톡이 먼저다. 그래서 함께 쓰는 곳이라고 적고, 순서가
scene에 달렸다는 사실을 그대로 덧붙인다.

등록소에 올리지 않는다
----------------------
이것들은 current의 대안이 아니라 current 안에서 쓰이는 곳이다. IMAGE
단계에 GENERATE로 올리면 화면이 "Imagen 대신 Pexels"를 고르게 만들고,
그 순간 이번 스프린트가 금지한 동작 변경이 된다.

그래서 자리는 만들되 등록소에는 올리지 않는다. 현재 이미지 엔진의
secondary_providers에 매달아 화면이 그것을 읽는다 - 같은 사실을 두
곳에서 관리하지 않는다.

부르면 정직하게 거절한다. 이 자리를 거쳐 스톡을 찾는 경로는 없다 -
엔진은 예전처럼 app.providers의 모듈을 곧바로 쓴다.
"""

import os

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    ProviderUnavailable,
    StageProvider,
)

# 엔진이 실제로 읽는 이름. 여기서 새로 정하지 않는다 -
# app/providers/pexels_provider.py와 pixabay_provider.py가 이 이름으로
# 읽는다. 두 값이 어긋나지 않도록 테스트가 잠근다.
PEXELS_KEY_SETTING = "PEXELS_API_KEY"
PIXABAY_KEY_SETTING = "PIXABAY_API_KEY"

# 순서가 scene에 달렸다는 사실. 어느 쪽이 먼저인지 화면이 지어내지
# 않도록 한 줄로 적어 둔다.
ORDER_NOTE = (
    "scene의 visual_type이 real이거나 없으면 스톡을 먼저 보고, ai면 "
    "Imagen을 먼저 봅니다."
)


class StockImageProvider(StageProvider):
    """
    현재 이미지 엔진이 안에서 쓰는 스톡 검색 자리.

    단계 Provider로 고를 수 있는 것이 아니다 - 등록소에 올리지 않고,
    부르면 거절한다.
    """

    # Sprint124의 자리들과 구분하는 표시. 코드가 있다는 뜻이다.
    coming_soon = False

    def __init__(self, name, display_name, vendor, key_setting, description):
        self._key_setting = key_setting

        self.capabilities = ProviderCapabilities(
            name=name,
            stage=stages.IMAGE,
            # 재 본 적이 없다. 등급을 매길 근거가 생기면 그때 바꾼다.
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

    def availability(self):
        """(쓸 수 있는가, 왜 못 쓰는가). 화면이 그대로 보여 준다."""

        if os.getenv(self._key_setting):
            return True, ""

        return False, f"{self._key_setting}가 설정되지 않았습니다."

    def is_configured(self) -> bool:
        return self.availability()[0]

    def generate(self, request):
        raise ProviderUnavailable(
            f"{self.capabilities.label}은(는) 현재 이미지 엔진이 안에서 "
            "쓰는 곳입니다. 단계 Provider로 고를 수 없습니다."
        )


# 이름 · 화면에 뜨는 이름 · 만든 곳 · 필요한 키 · 무엇을 찾는가.
#
# 이름은 provider_factory의 체인이 쓰는 앞자리와 같다(pexels_video의
# "pexels"). 어긋나면 화면이 말하는 곳과 실제로 찾는 곳이 갈린다.
STOCK_IMAGE_PROVIDERS = (
    ("pexels", "Pexels", "Pexels", PEXELS_KEY_SETTING,
     "동영상과 사진을 찾습니다. 체인에서 가장 먼저 봅니다."),
    ("pixabay", "Pixabay", "Pixabay", PIXABAY_KEY_SETTING,
     "동영상과 사진을 찾습니다. Pexels에서 못 찾으면 봅니다."),
)


def stock_image_providers():
    """자리를 만들어 돌려준다. 등록소에 올리지 않는다."""

    return [StockImageProvider(*entry) for entry in STOCK_IMAGE_PROVIDERS]


def stock_image_capabilities():
    """현재 이미지 엔진의 secondary_providers에 매달 것."""

    return tuple(p.capabilities for p in stock_image_providers())
