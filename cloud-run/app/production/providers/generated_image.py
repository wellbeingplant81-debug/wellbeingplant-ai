"""
Sprint132 - 실제로 붙은 이미지 Provider를 등록소에 올린다
(Epic 56, Phase 9).

Sprint130에 FLUX가, Sprint131에 GPT Image가 엔진 쪽에 붙었다. 그런데
등록소는 둘을 여전히 "향후 지원 예정"으로 들고 있었다. 화면은 등록소를
보고 목록을 그리므로, 되는 것을 안 된다고 말하고 있었던 셈이다 -
project.json에 직접 적어야만 닿았다.

여기서 맞춘다. 새 Provider를 만드는 것이 아니라, 이미 도는 것을
화면이 볼 수 있는 자리에 올린다.

Coming Soon과 설정 필요는 다르다
--------------------------------
    Coming Soon   코드가 없다. 키를 넣어도 안 된다
    설정 필요     코드는 있다. 키만 넣으면 된다

Sprint124가 만든 자리들은 앞쪽이고, 이 둘은 이제 뒤쪽이다. 그래서
못 쓰는 이유로 필요한 설정 이름을 그대로 말한다 - 화면이 그것을
그대로 보여 주면 사람이 무엇을 해야 하는지 안다.

파이프라인은 이 자리를 거치지 않는다
------------------------------------
이미지를 실제로 만드는 것은 asset_integration_service의 다리다
(Sprint127). 이 자리는 등록소의 목록이고, 부르면 그 다리가 쓰는 것과
같은 모듈로 간다 - 두 자리가 다른 모듈을 부르면 화면이 말하는 것과
실제로 도는 것이 갈린다. Sprint125의 ElevenLabs와 같은 구조다.
"""

import importlib
import os

from app.production import source_modes, stages
from app.production.stage_provider import (
    STANDARD,
    ProviderCapabilities,
    ProviderUnavailable,
    StageProvider,
)

IMAGES_DIRNAME = "images"


class GeneratedImageProvider(StageProvider):
    """이미지 한 장씩 만드는 Provider. 등록소에 올라가는 쪽."""

    # Sprint124의 자리들과 구분하는 표시. 코드가 있다는 뜻이다.
    coming_soon = False

    def __init__(self, name, display_name, vendor, key_setting, module_path,
                 description=""):
        self._key_setting = key_setting
        self._module_path = module_path

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

    # ---- 쓸 수 있는가 -------------------------------------------------

    def availability(self):
        """(쓸 수 있는가, 왜 못 쓰는가). 화면이 그대로 보여 준다."""

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
            raise ValueError(
                "이 단계에 필요한 값이 없습니다: ['project_path', 'scenes']"
            )

        request.require("project_path", "scenes")

        # 늦게 부른다 - 등록소에 올리는 것만으로 requests와 PIL 계층을
        # 끌고 오지 않는다.
        module = importlib.import_module(self._module_path)

        images_dir = os.path.join(request.project_path, IMAGES_DIRNAME)
        os.makedirs(images_dir, exist_ok=True)

        paths = []

        # 번호는 scene이 들고 있는 것을 쓴다 - 엔진이 그 번호로
        # scene{N}.png를 쓰므로, 여기서 다시 매기면 다른 파일이 나온다.
        for index, scene in enumerate(request.scenes, start=1):
            number = scene.get("scene", index)
            target = os.path.join(images_dir, f"scene{number}.png")

            module.generate_image(scene.get("image_prompt") or "", target)
            paths.append(target)

        return {"images": paths}


# 이름 · 화면에 뜨는 이름 · 만든 곳 · 필요한 키 · 실제로 부르는 모듈.
#
# 모듈 경로는 다리(asset_integration_service.SINGLE_IMAGE_PROVIDERS)가
# 쓰는 것과 같아야 한다. 갈라지면 화면이 말하는 것과 실제로 도는 것이
# 달라진다.
GENERATED_IMAGE_PROVIDERS = (
    ("flux", "FLUX", "Black Forest Labs", "FLUX_API_KEY",
     "app.providers.flux_provider",
     "FLUX로 이미지를 만듭니다. 현재 엔진의 Best-of-N·품질 게이트·"
     "스톡 폴백은 거치지 않고 한 장씩 만듭니다."),
    ("gpt_image", "GPT Image", "OpenAI", "OPENAI_API_KEY",
     "app.providers.gpt_image_provider",
     "GPT Image로 이미지를 만듭니다. 세로 크기가 1024x1536(2:3)이라 "
     "9:16으로 넣을 때 가로가 약 15% 잘립니다."),
)


def generated_image_providers():
    """등록할 것들을 만들어 돌려준다. 여기서 등록하지 않는다 -
    등록은 bootstrap이 명시적으로 부를 때만 일어난다(Sprint103)."""

    return [GeneratedImageProvider(*entry)
            for entry in GENERATED_IMAGE_PROVIDERS]
