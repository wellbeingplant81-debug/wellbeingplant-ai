"""
Sprint103 - 지금 엔진을 등록소에 올린다 (Epic 54, Phase 2).

등록은 명시적으로 부를 때만 일어난다. 모듈을 import하는 것만으로
등록되게 만들면, 무엇이 언제 등록됐는지 추적할 수 없고 테스트마다
등록소 상태가 달라진다.

같은 이유로 두 번 불러도 안전하다 - 이미 있으면 다시 올리지 않는다.

Music 단계는 등록하지 않는다. 지금 BGM은 bgm_service가 영상 렌더 중에
섞어 넣고 별도 산출물이 없다 - 그것을 "만들어 오는 것"으로 감싸려면
렌더 경로를 건드려야 하고, 이번 스프린트는 엔진을 수정하지 않는다.
등록소가 music을 비워 두는 것이 지금의 사실이다.
"""

from typing import List

from app.production.providers.chat_import import ChatImportScriptProvider
from app.production.providers.image_import import ImageImportProvider
from app.production.providers.voice_import import VoiceImportProvider
from app.production.providers.current_engine import CURRENT_PROVIDER_CLASSES
from app.production.registry import StageProviderRegistry, default_registry
from app.production.stage_provider import StageProvider


def register_current_providers(
    registry: StageProviderRegistry = None,
) -> List[StageProvider]:
    """
    지금 파이프라인이 쓰는 엔진들을 Provider로 올린다.

    이미 올라가 있으면 건너뛴다 - 두 번 불러도 예외가 나지 않는다.
    올린 것만 돌려준다.
    """

    registry = default_registry() if registry is None else registry
    registered = []

    # Sprint104/110/112 - 붙여넣기와 직접 업로드 경로도 함께 올린다.
    # 전부 GENERATE를 지원하지 않으므로 Auto 모드가 이것들을 고르는
    # 일은 없다 - registry.select()가 source_mode로 먼저 거른다.
    for provider_class in CURRENT_PROVIDER_CLASSES + (
        ChatImportScriptProvider, ImageImportProvider, VoiceImportProvider,
    ):
        provider = provider_class()

        try:
            registry.get(provider.stage, provider.name)
        except ValueError:
            registry.register(provider)
            registered.append(provider)

    return registered


def is_bootstrapped(registry: StageProviderRegistry = None) -> bool:
    registry = default_registry() if registry is None else registry

    for provider_class in CURRENT_PROVIDER_CLASSES:
        stage = provider_class.stage_name
        try:
            registry.get(stage, "current")
        except ValueError:
            return False

    return True
