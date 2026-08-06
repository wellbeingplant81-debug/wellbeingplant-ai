"""
Sprint102 - Provider 등록소 (Epic 54, Architecture Phase 1).

app/providers/upload/provider_registry.py(Sprint89 이식)와 같은 모양이다.
새 Registry 개념을 만들지 않았다 - 단계별로 여러 개가 등록된다는 점만
다르다(upload는 플랫폼당 하나였다).

등록 시점에 선언을 검증한다. 잘못 선언된 Provider가 조용히 들어와
있다가 실제 제작 중에 터지는 것보다, 등록에서 막히는 편이 싸다.

이번 스프린트에는 등록되는 Provider가 하나도 없다. 빈 등록소를
돌려주는 것이 지금의 사실이다 - 화면은 "선택 가능한 Provider 없음"을
그대로 보여줘야 하고, 없는 목록을 지어내지 않는다.
"""

from typing import Dict, List, Optional

from app.production import source_modes, stages
from app.production.stage_provider import (
    QUALITY_ORDER,
    StageProvider,
    validate_capabilities,
)


class StageProviderRegistry:

    def __init__(self):
        self._providers: Dict[str, List[StageProvider]] = {
            stage: [] for stage in stages.STAGES
        }

    def register(self, provider: StageProvider) -> StageProvider:
        validate_capabilities(provider.capabilities)

        stage = provider.stage
        existing = [p.name for p in self._providers[stage]]

        if provider.name in existing:
            raise ValueError(
                f"{stage} 단계에 이미 등록된 이름입니다: {provider.name}"
            )

        self._providers[stage].append(provider)

        return provider

    def for_stage(self, stage: str) -> List[StageProvider]:
        stages.require_stage(stage)

        return list(self._providers[stage])

    def get(self, stage: str, name: str) -> StageProvider:
        for provider in self.for_stage(stage):
            if provider.name == name:
                return provider

        raise ValueError(f"{stage} 단계에 등록되지 않은 Provider입니다: {name}")

    def available(self, stage: str, source_mode: str = None) -> List[StageProvider]:
        """지금 실제로 쓸 수 있는 것만. 자격증명이 없는 Provider는
        빠진다 - 목록에 있는데 누르면 실패하는 상황을 만들지 않는다."""

        found = [p for p in self.for_stage(stage) if p.is_available()]

        if source_mode is not None:
            source_modes.require_source_mode(source_mode)
            found = [p for p in found if p.supports(source_mode)]

        return found

    def select(self, stage: str, quality_preference,
               source_mode: str = source_modes.GENERATE) -> Optional[StageProvider]:
        """
        정책이 선호하는 품질 순서대로 고른다.

        선호 등급에 해당하는 것이 여럿이면 그중 품질이 가장 높은 것을
        고른다 - Premium 모드가 "premium 등급 중 아무거나"로 끝나지
        않게 한다.

        쓸 수 있는 것이 없으면 None이다. 아무거나 대신 고르지 않는다.
        """

        candidates = self.available(stage, source_mode)

        if not candidates:
            return None

        for tier in quality_preference:
            matching = [p for p in candidates if p.capabilities.quality_tier == tier]
            if matching:
                return min(
                    matching,
                    key=lambda p: QUALITY_ORDER[p.capabilities.quality_tier],
                )

        return None

    def __len__(self) -> int:
        return sum(len(v) for v in self._providers.values())


# 저장소 전체가 공유하는 등록소. 지금은 비어 있다.
_registry = StageProviderRegistry()


def default_registry() -> StageProviderRegistry:
    return _registry
