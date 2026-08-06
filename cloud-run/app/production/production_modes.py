"""
Sprint102 - 제작 방식 (Epic 54, Architecture Phase 1).

영상을 만들기 시작할 때 고르는 다섯 가지다.

    AUTO_PREMIUM    전부 AI가 만든다. 품질이 유일한 기준이다.
    AUTO_STANDARD   전부 AI가 만든다. 품질과 비용을 함께 본다.
    AUTO_ECONOMY    전부 AI가 만든다. 비용을 줄이는 것이 목표다.
    ASSISTED        단계마다 사용자가 고른다.
    MANUAL          사용자가 다 준다. 우리는 영상만 만든다.

여기서 가장 중요한 규칙 하나를 코드로 못 박는다.

    Auto Premium은 "자동이라서 대충"이 아니다.

이 저장소에서 자동화는 곧잘 "싸게 빨리"와 같은 말로 쓰였다. Premium은
정반대다 - 사람이 직접 만든 것과 견줘도 밀리지 않아야 하고, 그러기
위해 비용을 더 쓰는 것이 정상이다. 그래서 PREMIUM 정책에는 비용
상한이 없고(cost_ceiling=None), Provider를 고르는 축이 품질 하나다.
비용을 기준으로 삼는 것은 ECONOMY 하나뿐이다.

품질 등급 이름을 모드 이름과 같게 둔 것도 같은 이유다 - "Premium
모드는 premium 등급을 고른다"가 규칙의 전부여야, 나중에 아무도 그
사이에 다른 기준을 몰래 끼워 넣지 못한다.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from app.production import source_modes, stage_provider

AUTO_PREMIUM = "auto_premium"
AUTO_STANDARD = "auto_standard"
AUTO_ECONOMY = "auto_economy"
ASSISTED = "assisted"
MANUAL = "manual"

PRODUCTION_MODES = (
    AUTO_PREMIUM, AUTO_STANDARD, AUTO_ECONOMY, ASSISTED, MANUAL,
)

LABELS = {
    AUTO_PREMIUM: "Auto Premium",
    AUTO_STANDARD: "Auto Standard",
    AUTO_ECONOMY: "Auto Economy",
    ASSISTED: "Assisted",
    MANUAL: "Manual",
}

DESCRIPTIONS = {
    AUTO_PREMIUM: "전부 자동. 가장 좋은 결과를 목표로 하고 비용을 아끼지 않습니다.",
    AUTO_STANDARD: "전부 자동. 품질과 비용의 균형을 봅니다.",
    AUTO_ECONOMY: "전부 자동. 비용을 최대한 줄입니다.",
    ASSISTED: "단계마다 AI 생성 / 붙여넣기 / 직접 작성을 고릅니다.",
    MANUAL: "대본·이미지·음성을 직접 주면 영상만 만듭니다. API를 부르지 않습니다.",
}


@dataclass(frozen=True)
class ModePolicy:
    """이 모드가 Provider와 입력 방식을 고르는 규칙."""

    mode: str
    # 이 모드가 허용하는 입력 방식. 사용자가 고를 수 있는 범위이자,
    # Plan 검증이 보는 기준이다.
    allowed_source_modes: Tuple[str, ...]
    # 자동으로 고를 때 선호하는 품질 등급 순서(앞에서부터 찾는다).
    # 사용자가 직접 고르는 모드는 비어 있다.
    quality_preference: Tuple[str, ...] = ()
    # 비용 상한. None은 "상한 없음"이다 - Premium이 그렇다.
    cost_ceiling: Optional[float] = None
    # 사용자가 단계마다 직접 고르는가.
    user_chooses_per_stage: bool = False
    # 품질이 기준에 못 미치면 자동으로 다시 만드는가.
    auto_regenerate: bool = False


_PREMIUM = ModePolicy(
    mode=AUTO_PREMIUM,
    allowed_source_modes=(source_modes.GENERATE,),
    # 품질 하나만 본다. 상위 등급이 있으면 무조건 그것을 고른다.
    quality_preference=(
        stage_provider.PREMIUM, stage_provider.STANDARD, stage_provider.ECONOMY,
    ),
    # 상한 없음. Premium의 정의다.
    cost_ceiling=None,
    auto_regenerate=True,
)

_STANDARD = ModePolicy(
    mode=AUTO_STANDARD,
    allowed_source_modes=(source_modes.GENERATE,),
    quality_preference=(
        stage_provider.STANDARD, stage_provider.PREMIUM, stage_provider.ECONOMY,
    ),
    cost_ceiling=None,
    auto_regenerate=True,
)

_ECONOMY = ModePolicy(
    mode=AUTO_ECONOMY,
    allowed_source_modes=(source_modes.GENERATE,),
    quality_preference=(
        stage_provider.ECONOMY, stage_provider.STANDARD, stage_provider.PREMIUM,
    ),
    cost_ceiling=None,
    # 비용을 줄이는 모드에서 자동 재생성은 앞뒤가 맞지 않는다 -
    # 재생성이 비용을 가장 크게 늘리는 항목이다.
    auto_regenerate=False,
)

_ASSISTED = ModePolicy(
    mode=ASSISTED,
    allowed_source_modes=source_modes.SOURCE_MODES,
    user_chooses_per_stage=True,
)

_MANUAL = ModePolicy(
    mode=MANUAL,
    # GENERATE가 없다. 이 모드는 API를 부르지 않는다.
    allowed_source_modes=(source_modes.IMPORT, source_modes.MANUAL),
    user_chooses_per_stage=True,
)

POLICIES = {
    AUTO_PREMIUM: _PREMIUM,
    AUTO_STANDARD: _STANDARD,
    AUTO_ECONOMY: _ECONOMY,
    ASSISTED: _ASSISTED,
    MANUAL: _MANUAL,
}

# 지금 파이프라인이 하는 일과 같은 모드. 기존 동작이 어디에
# 해당하는지 분명히 해 둔다 - 이 저장소는 지금까지 이 하나만 했다.
CURRENT_ENGINE_MODE = AUTO_STANDARD


def is_production_mode(value: str) -> bool:
    return value in PRODUCTION_MODES


def require_production_mode(value: str) -> str:
    if not is_production_mode(value):
        raise ValueError(
            f"알 수 없는 제작 방식입니다: {value!r}. "
            f"사용 가능한 값: {list(PRODUCTION_MODES)}"
        )
    return value


def policy_for(mode: str) -> ModePolicy:
    return POLICIES[require_production_mode(mode)]


def is_automatic(mode: str) -> bool:
    return not policy_for(mode).user_chooses_per_stage


def calls_api(mode: str) -> bool:
    """이 모드가 API를 부를 수 있는가.

    MANUAL만 False다 - 그 모드의 허용 목록에 GENERATE가 없다. 별도
    플래그를 두지 않고 허용 목록에서 유도하는 이유는, 목록과 플래그가
    어긋나는 순간 둘 중 무엇이 진실인지 알 수 없게 되기 때문이다."""

    return any(
        source_modes.calls_api(m) for m in policy_for(mode).allowed_source_modes
    )
