"""
Sprint218 - 무엇으로 만들 것인가, 그리고 돈이 들 수 있는가 (Epic 62).

새 모드 체계를 만들지 않는다
----------------------------
이 저장소에는 이미 production_modes(Sprint102)가 있고 그것이 다섯
방식과 각 방식의 정책을 들고 있다. 여기에 여섯째를 더하거나 평행한
enum을 새로 세우면, 어느 날 두 목록이 서로 다른 말을 한다.

이 파일이 하는 일은 그 위에 **사람이 고를 두 갈래**를 얹는 것뿐이다.

    FREE        내 PC에 있는 것으로만 만든다. 외부 AI를 부르지 않는다
    FULL_AUTO   AI가 대본부터 렌더까지 이어서 만든다

그 둘이 실제로 어느 production_mode인지는 아래 표 하나가 정하고,
"돈이 들 수 있는가"는 그 모드에서 유도한다 - 따로 적어 두면 모드를
바꿀 때 한쪽만 바뀐다.

돈이 든다고 단정하지 않는다
---------------------------
이 파일이 답할 수 있는 것은 "외부 유료 API를 부를 수 있는가"까지다.
실제로 얼마가 나가는지는 단가를 아는 단계만 계산되고(cost.py) 모르는
단계가 남는다 - 그래서 화면에 적는 말은 "발생할 수 있습니다"이고,
금액은 아는 것만 적는다. 모르는 값을 지어내지 않는다.

무엇을 하지 않는가
------------------
결제하지 않는다. 결제 수단도 만들지 않는다. 이 Sprint가 하는 일은
"유료일 수 있는 일을 시작하기 전에 사람에게 말하고 확인을 받는다"
하나다.
"""

from dataclasses import dataclass
from typing import Tuple

from app.production import production_modes, source_modes

FREE = "free"
FULL_AUTO = "full_auto"

CREATION_MODES = (FREE, FULL_AUTO)

LABELS = {
    FREE: "무료로 만들기",
    FULL_AUTO: "완전 자동으로 만들기",
}

# 화면에 적는 설명. **지금 실제로 되는 것만 적는다.**
#
# 처음 초안은 FULL_AUTO를 "소재 분석부터 대본·장면 구성·소스 선택·
# 음성·편집·렌더링까지"라고 적었다. 이 저장소가 실제로 하는 것과
# 맞춰 보니 "소재 분석"에 해당하는 단계가 없다 - 주제는 사람이 적고,
# 파이프라인은 그 주제로 대본부터 시작한다(step01). 그래서 그 말을
# 뺐다. 있는 척하는 설명 한 줄이 나머지 전부를 의심스럽게 만든다.
DESCRIPTIONS = {
    FREE: "내 PC에 있는 자료와 목소리로 만듭니다. "
          "외부 AI를 부르지 않아 비용이 들지 않습니다.",
    FULL_AUTO: "적어 주신 주제로 AI가 대본 · 장면 · 이미지 · 음성 · "
               "자막을 만들고 영상까지 렌더링합니다.",
}

# 각 갈래가 실제로 어느 production_mode인가.
#
# FULL_AUTO가 CURRENT_ENGINE_MODE인 이유 - 파이프라인이 지금까지 실제로
# 해 온 일이 그 모드다(production_modes가 그렇게 적어 두었다). 여기서
# AUTO_PREMIUM을 가리키면 화면은 "가장 좋은 것으로 만든다"고 말하지만
# 엔진은 여전히 같은 일을 한다 - 그것이 가짜 자동화다.
PRODUCTION_MODE = {
    FREE: production_modes.MANUAL,
    FULL_AUTO: production_modes.CURRENT_ENGINE_MODE,
}


@dataclass(frozen=True)
class CostPolicy:
    """
    이 갈래를 실행하면 돈이 들 수 있는가.

    앞으로 Provider가 늘어난다(AI Bridge · 로컬 AI · 유료 API). 그때
    바뀌는 것은 "어느 Provider가 유료인가"이고, 이 층이 묻는 물음은
    그대로다 - 그래서 Provider를 여기 적지 않고 모드에서 유도한다.
    """

    creation_mode: str
    # 유료 API를 부를 수 있는가. "부른다"가 아니다.
    may_cost: bool
    # 시작하기 전에 사람의 확인을 받아야 하는가.
    requires_confirmation: bool
    # 왜 그렇게 판정했는가. 화면이 그대로 보여 준다.
    reason: str
    # API를 부를 수 있는 단계들(사람이 읽는 이름).
    api_stages: Tuple[str, ...] = ()


def is_creation_mode(value: str) -> bool:
    return value in CREATION_MODES


def require_creation_mode(value: str) -> str:
    if not is_creation_mode(value):
        raise ValueError(
            f"알 수 없는 제작 방식입니다: {value!r}. "
            f"사용 가능한 값: {list(CREATION_MODES)}"
        )

    return value


def production_mode_for(creation_mode: str) -> str:
    return PRODUCTION_MODE[require_creation_mode(creation_mode)]


def calls_paid_api(creation_mode: str) -> bool:
    """
    이 갈래가 유료 API를 부를 수 있는가.

    production_modes.calls_api()에서 유도한다 - 그 함수는 다시 모드의
    허용 입력 목록에서 유도한다. 플래그를 따로 두지 않는 이 저장소의
    관례를 그대로 잇는다.
    """

    return production_modes.calls_api(production_mode_for(creation_mode))


def api_stage_labels(creation_mode: str) -> Tuple[str, ...]:
    """
    이 갈래에서 API를 부를 수 있는 단계들.

    지어내지 않는다 - 그 모드의 자동 계획을 실제로 세워서, 계획이
    API를 부른다고 말하는 단계만 가져온다.
    """

    if not calls_paid_api(creation_mode):
        return ()

    from app.production import stages
    from app.production.production_plan import build_automatic_plan

    try:
        # 등록소를 채워서 묻는다.
        #
        # default_registry()는 비어 있다. 비운 채로 물으면 계획에
        # 선택이 하나도 없고, 그러면 "API를 부르는 단계 없음"이라는
        # 답이 돌아온다 - 실제로는 전부 부르는데도(실측). 라우터가
        # 계획을 세울 때 쓰는 것과 같은 bootstrap을 쓴다.
        from app.production.providers import bootstrap
        from app.production.registry import StageProviderRegistry

        registry = StageProviderRegistry()
        bootstrap.register_current_providers(registry)

        plan = build_automatic_plan(
            production_mode_for(creation_mode), registry=registry)
    except Exception:
        # 계획을 못 세우는 자리에서도 안내는 떠야 한다. 안내가 못 뜨면
        # 확인을 받을 수 없고, 그러면 시작할 방법이 없다. 단계 이름만
        # 비워 두고 나머지는 그대로 말한다.
        return ()

    return tuple(
        stages.LABELS.get(stage, stage) for stage in plan.api_stages
    )


def cost_policy_for(creation_mode: str) -> CostPolicy:
    """이 갈래의 과금 정책. 화면과 라우터가 이것만 본다."""

    require_creation_mode(creation_mode)

    may_cost = calls_paid_api(creation_mode)

    if not may_cost:
        return CostPolicy(
            creation_mode=creation_mode,
            may_cost=False,
            requires_confirmation=False,
            reason="외부 AI를 부르지 않습니다. 내 PC에 있는 자료와 "
                   "목소리만 씁니다.",
        )

    return CostPolicy(
        creation_mode=creation_mode,
        may_cost=True,
        requires_confirmation=True,
        reason="AI 이미지 · 음성 · 대본 등 외부 AI 서비스를 부릅니다. "
               "쓰는 서비스와 만드는 내용에 따라 비용이 발생할 수 "
               "있습니다.",
        api_stages=api_stage_labels(creation_mode),
    )


def needs_cost_confirmation(creation_mode: str) -> bool:
    return cost_policy_for(creation_mode).requires_confirmation


def allowed_source_modes(creation_mode: str) -> Tuple[str, ...]:
    """이 갈래가 허용하는 입력 방식. Plan 검증이 보는 그 목록이다."""

    return production_modes.policy_for(
        production_mode_for(creation_mode)).allowed_source_modes


def as_dict(creation_mode: str) -> dict:
    """화면이 그릴 한 덩이."""

    policy = cost_policy_for(creation_mode)

    return {
        "creation_mode": creation_mode,
        "label": LABELS[creation_mode],
        "description": DESCRIPTIONS[creation_mode],
        "production_mode": production_mode_for(creation_mode),
        "production_mode_label": production_modes.LABELS[
            production_mode_for(creation_mode)],
        "may_cost": policy.may_cost,
        "requires_confirmation": policy.requires_confirmation,
        "cost_reason": policy.reason,
        "api_stages": list(policy.api_stages),
        "allowed_source_modes": list(allowed_source_modes(creation_mode)),
        "calls_api": policy.may_cost,
    }


def all_as_dict() -> list:
    return [as_dict(mode) for mode in CREATION_MODES]


# source_modes를 여기서 다시 세지 않는다는 것을 눈에 보이게 남겨 둔다 -
# FREE가 API를 안 부른다는 사실의 출처는 이 모듈이 아니라 그쪽이다.
assert not any(
    source_modes.calls_api(m) for m in allowed_source_modes(FREE)
), "FREE가 API를 부를 수 있는 입력 방식을 허용하고 있습니다"
