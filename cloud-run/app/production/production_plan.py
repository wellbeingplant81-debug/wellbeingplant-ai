"""
Sprint102 - 제작 계획 (Epic 54, Architecture Phase 1).

"이 영상을 어떤 방식으로, 각 단계를 무엇으로 만들 것인가"를 한 곳에
적어 둔 것이다. 영상 생성이 시작되기 전에 완성되고, 그 뒤로는 바뀌지
않는다.

Plan을 따로 두는 이유가 있다. 지금 파이프라인은 무엇을 쓸지를 실행
중에 그때그때 정한다 - config 플래그를 보고, 환경변수를 보고, scene을
보고. 그래서 "이 영상이 무엇으로 만들어졌는가"를 나중에 알 수 없고,
만들기 전에 비용을 계산할 수도 없다. Plan은 그 결정을 실행보다 앞으로
당긴다.

이번 스프린트는 Plan을 만들기만 하고 실행하지 않는다. 파이프라인은
지금까지 하던 대로 돈다.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.production import production_modes, source_modes, stages
from app.production.cost import CostBreakdown
from app.production.registry import StageProviderRegistry, default_registry


@dataclass(frozen=True)
class StageSelection:
    """한 단계를 무엇으로, 어떻게 만들 것인가."""

    stage: str
    source_mode: str
    provider: Optional[str] = None
    # IMPORT/MANUAL일 때 사용자가 준 것. 붙여넣은 텍스트이거나 파일
    # 경로다. Plan은 내용을 해석하지 않는다 - 나르기만 한다.
    payload: Optional[object] = None

    @property
    def calls_api(self) -> bool:
        return source_modes.calls_api(self.source_mode)


class PlanError(ValueError):
    """계획 자체가 성립하지 않는다. 만들기 전에 잡는다."""


@dataclass
class ProductionPlan:

    mode: str
    selections: Dict[str, StageSelection] = field(default_factory=dict)

    @property
    def policy(self):
        return production_modes.policy_for(self.mode)

    @property
    def calls_api(self) -> bool:
        """이 계획이 API를 부르는가. Manual 모드의 계약이 이것이다."""

        return any(s.calls_api for s in self.selections.values())

    @property
    def api_stages(self) -> List[str]:
        return sorted(s.stage for s in self.selections.values() if s.calls_api)

    def select(self, selection: StageSelection) -> "ProductionPlan":
        stages.require_stage(selection.stage)
        source_modes.require_source_mode(selection.source_mode)

        # Sprint109 - 모드가 허용하는 것과 단계가 허용하는 것 둘 다
        # 만족해야 한다. 대본은 건너뛸 수 없고, Manual 모드에서는
        # AI 생성을 고를 수 없다.
        allowed_here = stages.allowed_source_modes(selection.stage)

        if selection.source_mode not in allowed_here:
            raise PlanError(
                f"{stages.LABELS[selection.stage]} 단계에는 "
                f"{source_modes.LABELS[selection.source_mode]}을(를) "
                f"쓸 수 없습니다. 허용: "
                f"{[source_modes.LABELS[m] for m in allowed_here]}"
            )

        allowed = self.policy.allowed_source_modes

        if selection.source_mode not in allowed:
            raise PlanError(
                f"{production_modes.LABELS[self.mode]}에서는 "
                f"{stages.LABELS[selection.stage]} 단계에 "
                f"{source_modes.LABELS[selection.source_mode]}을(를) "
                f"쓸 수 없습니다. 허용: "
                f"{[source_modes.LABELS[m] for m in allowed]}"
            )

        self.selections[selection.stage] = selection

        return self

    def missing_stages(self) -> List[str]:
        return [s for s in stages.STAGES if s not in self.selections]

    def validate(self) -> "ProductionPlan":
        """만들기 전에 확인한다.

        빠진 단계를 조용히 기본값으로 채우지 않는다 - 사용자가 고르지
        않은 것을 우리가 정해 버리면, 결과가 마음에 안 들 때 왜 그렇게
        됐는지 아무도 설명할 수 없다."""

        missing = self.missing_stages()

        if missing:
            raise PlanError(
                "계획이 덜 찼습니다: "
                f"{[stages.LABELS[s] for s in missing]}"
            )

        for selection in self.selections.values():
            if selection.calls_api and not selection.provider:
                raise PlanError(
                    f"{stages.LABELS[selection.stage]} 단계가 AI 생성인데 "
                    "Provider가 정해지지 않았습니다."
                )
            if selection.source_mode == source_modes.NONE:
                # 건너뛰는 단계는 줄 것도 고를 것도 없다.
                continue
            if not selection.calls_api and selection.payload is None:
                raise PlanError(
                    f"{stages.LABELS[selection.stage]} 단계가 "
                    f"{source_modes.LABELS[selection.source_mode]}인데 "
                    "받은 내용이 없습니다."
                )

        return self

    def estimate_cost(
        self, request=None, registry: StageProviderRegistry = None,
    ) -> CostBreakdown:
        """
        예상 비용. 숫자를 지어내지 않는다.

        Provider가 등록돼 있지 않거나 단가를 모르면 그 단계는
        unknown으로 남는다 - CostBreakdown이 그것을 숨기지 않는다.
        """

        registry = default_registry() if registry is None else registry
        breakdown = CostBreakdown()

        for stage in stages.STAGES:
            selection = self.selections.get(stage)

            if selection is None:
                continue

            if not selection.calls_api:
                from app.production.cost import free_estimate

                note = (
                    "이 단계를 건너뜁니다."
                    if selection.source_mode == source_modes.NONE
                    else "API를 호출하지 않습니다."
                )
                breakdown.add(free_estimate(
                    stage, selection.provider or "-", selection.source_mode,
                    note=note,
                ))
                continue

            try:
                provider = registry.get(stage, selection.provider)
            except ValueError:
                from app.production.cost import CostEstimate

                breakdown.add(CostEstimate(
                    stage=stage, provider=selection.provider or "-",
                    source_mode=selection.source_mode, amount=None,
                    note="등록되지 않은 Provider라 단가를 알 수 없습니다.",
                ))
                continue

            breakdown.add(provider.estimate_cost(request, selection.source_mode))

        return breakdown

    def estimate_seconds(self) -> float:
        """이 계획으로 만들면 얼마나 걸리는가.

        만드는 단계만 시간이 든다 - 붙여넣거나 직접 준 것은 만들
        시간이 없고, 건너뛴 것은 아예 돌지 않는다. 자막/렌더/썸네일/
        품질은 무엇을 고르든 항상 돌므로 늘 더해진다.

        숫자는 stage_timing이 갖고 있고 그것은 실측 37편의 중앙값이다.
        """

        from app.production import stage_timing

        total = stage_timing.FIXED_SECONDS

        for selection in self.selections.values():
            if selection.calls_api:
                total += stage_timing.seconds_for(selection.stage)

        return round(total, 1)

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "label": production_modes.LABELS[self.mode],
            "calls_api": self.calls_api,
            "api_stages": self.api_stages,
            "estimated_seconds": self.estimate_seconds(),
            "stages": {
                stage: {
                    "source_mode": s.source_mode,
                    "provider": s.provider,
                    "has_payload": s.payload is not None,
                }
                for stage, s in self.selections.items()
            },
        }


def build_automatic_plan(
    mode: str, registry: StageProviderRegistry = None,
) -> ProductionPlan:
    """
    Auto 모드의 계획을 등록소에서 만든다.

    사용자가 단계마다 고르는 모드(Assisted/Manual)에는 쓰지 않는다 -
    그 모드의 계획은 화면이 사용자의 선택으로 채운다.

    쓸 수 있는 Provider가 없는 단계는 비워 둔다. 여기서 예외를 던지지
    않는 이유는, "무엇이 왜 비었는지"를 화면이 보여줘야 하기 때문이다 -
    validate()가 그때 막는다.
    """

    policy = production_modes.policy_for(mode)

    if policy.user_chooses_per_stage:
        raise PlanError(
            f"{production_modes.LABELS[mode]}은(는) 단계마다 사용자가 "
            "고르는 방식이라 자동으로 계획을 만들 수 없습니다."
        )

    registry = default_registry() if registry is None else registry
    plan = ProductionPlan(mode=mode)

    for stage in stages.STAGES:
        provider = registry.select(
            stage, policy.quality_preference, source_modes.GENERATE,
        )

        if provider is None:
            continue

        plan.select(StageSelection(
            stage=stage, source_mode=source_modes.GENERATE,
            provider=provider.name,
        ))

    return plan
