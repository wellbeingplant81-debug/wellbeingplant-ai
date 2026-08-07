"""
Sprint102 - Provider 계약 (Epic 54, Architecture Phase 1).

한 단계(대본/이미지/음성/음악/메타데이터)의 결과물을 만들어 오는
것의 공통 모양이다. 이번 스프린트는 구현을 하나도 만들지 않는다 -
계약만 세운다.

세 입력 방식이 한 클래스에 모여 있는 이유가 있다. 사용자에게는
"대본을 어떻게 만들까"라는 하나의 선택이고, 그 선택지가 AI 생성 /
붙여넣기 / 직접 작성일 뿐이다. 세 개의 다른 클래스로 쪼개면 화면과
Plan이 그 셋을 다시 하나로 묶는 코드를 갖게 된다.

Provider가 세 방식을 다 지원할 필요는 없다. supported_source_modes로
자기가 할 수 있는 것만 선언하고, 못 하는 것을 부르면 예외가 난다 -
조용히 빈 결과를 돌려주지 않는다.

기존 구조를 흉내내지 않고 실제로 재사용한다. 이 계약은 upload 쪽
UploadProvider(Sprint89 이식)와 같은 성격이고, Registry도 같은 모양을
따른다(app/providers/upload/provider_registry.py).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Tuple

from app.production import source_modes, stages
from app.production.cost import CostEstimate, free_estimate

# 품질 등급. Auto 모드가 Provider를 고를 때 쓰는 축이다.
#
# 이름을 모드와 같게 둔 것은 의도다 - Auto Premium이 PREMIUM 등급을
# 고른다는 것이 규칙의 전부여야 하고, 그 사이에 번역표가 끼면 "Premium
# 모드인데 왜 저 Provider가 골라졌는가"를 아무도 설명할 수 없게 된다.
PREMIUM = "premium"
STANDARD = "standard"
ECONOMY = "economy"

QUALITY_TIERS = (PREMIUM, STANDARD, ECONOMY)

# 품질 내림차순. Auto Premium은 앞에서부터, Auto Economy는 뒤에서부터
# 고른다.
QUALITY_ORDER = {PREMIUM: 0, STANDARD: 1, ECONOMY: 2}


@dataclass(frozen=True)
class ProviderCapabilities:
    """이 Provider가 무엇을 할 수 있는지. 화면과 Plan이 이것만 보고
    판단할 수 있어야 한다 - Provider를 실제로 불러 보고 알아내지
    않는다."""

    name: str
    stage: str
    quality_tier: str = STANDARD
    supported_source_modes: Tuple[str, ...] = (source_modes.GENERATE,)
    # 켜려면 무엇이 있어야 하는가(환경변수/자격증명 이름). 화면이
    # "왜 이 Provider를 못 쓰는지" 말할 수 있게 한다.
    required_settings: Tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    # Sprint124 - 화면이 Provider를 고르게 하려면 이름만으로는 부족하다.
    #
    # display_name은 사람에게 보일 이름, vendor는 누가 만든 것인가다.
    # name은 코드가 쓰는 열쇠라 그대로 둔다.
    display_name: str = ""
    vendor: str = ""
    # 한 편에 얼마나 드는가. 모르면 None이다 - 0.0과 다르다. 0.0은
    # 무료임을 안다는 뜻이고, None은 아직 모른다는 뜻이다. 지어내지
    # 않는다.
    estimated_cost: Optional[float] = None
    # 만드는 중간을 흘려 보낼 수 있는가. 지원 방식에서 유도할 수 없어
    # 따로 둔다.
    supports_streaming: bool = False

    def supports(self, source_mode: str) -> bool:
        return source_mode in self.supported_source_modes

    # 아래 셋은 supported_source_modes에서 유도한다. 따로 적어 두면
    # 한쪽만 바뀌는 날이 온다 - 이 저장소에서 한 슬롯을 두 곳에서
    # 쓰는 구조는 이미 여러 번 사고를 냈다.
    @property
    def supports_generate(self) -> bool:
        return self.supports(source_modes.GENERATE)

    @property
    def supports_import(self) -> bool:
        return self.supports(source_modes.IMPORT)

    @property
    def supports_manual(self) -> bool:
        return self.supports(source_modes.MANUAL)

    @property
    def label(self) -> str:
        """사람에게 보일 이름. 없으면 코드가 쓰는 이름을 그대로."""

        return self.display_name or self.name


class StageProviderError(RuntimeError):
    """Provider가 할 수 없는 것을 요구받았다."""


class ProviderUnavailable(StageProviderError):
    """자리는 있지만 아직 붙지 않았다.

    "지원하지 않는다"와 다르다 - 그것은 영영 안 되는 것이고, 이것은
    아직 안 된 것이다. 되는 척하지 않으려고 이름을 나눈다."""


class StageProvider(ABC):
    """
    한 단계의 결과물을 만들어 오는 것.

    구현체는 capabilities를 반드시 채운다. 나머지 세 메서드는 자기가
    선언한 방식만 구현하면 된다 - 선언하지 않은 것은 기본 구현이
    StageProviderError를 던진다.
    """

    capabilities: ProviderCapabilities

    @property
    def name(self) -> str:
        return self.capabilities.name

    @property
    def stage(self) -> str:
        return self.capabilities.stage

    def supports(self, source_mode: str) -> bool:
        return self.capabilities.supports(source_mode)

    def _require(self, source_mode: str) -> None:
        if not self.supports(source_mode):
            raise StageProviderError(
                f"{self.name}은(는) {source_mode} 방식을 지원하지 않습니다. "
                f"지원: {list(self.capabilities.supported_source_modes)}"
            )

    # ---- 세 가지 입력 방식 -------------------------------------------

    def generate(self, request):
        """API를 불러 만든다. 유일하게 돈이 드는 경로다."""

        self._require(source_modes.GENERATE)
        raise NotImplementedError

    def import_content(self, raw: str, request=None):
        """
        다른 곳에서 만들어 온 것을 받는다.

        raw는 사용자가 GPT/Claude/Gemini/DeepSeek 웹 채팅에서 복사해
        붙여넣은 텍스트 그대로다. 모델마다 답의 모양이 다르고(코드
        펜스, 앞뒤 설명 문장, JSON 아닌 산문) 그것을 우리 형식으로
        옮기는 것이 이 메서드의 일이다.

        파싱에 실패하면 예외를 던진다 - 반쯤 읽은 결과로 영상을
        만들지 않는다. 무엇이 왜 안 읽혔는지 사람이 고칠 수 있게
        메시지에 담는다.
        """

        self._require(source_modes.IMPORT)
        raise NotImplementedError

    def accept_manual(self, payload, request=None):
        """사용자가 직접 쓴 것 / 올린 파일을 그대로 받는다.

        여기서는 파싱도 검증 이상의 가공도 하지 않는다 - 사용자가
        준 것이 곧 결과다."""

        self._require(source_modes.MANUAL)
        raise NotImplementedError

    # ---- 비용 -------------------------------------------------------

    def estimate_cost(self, request, source_mode: str) -> CostEstimate:
        """
        이 방식으로 이 요청을 처리하면 얼마가 드는가.

        기본 구현은 두 가지만 안다 - API를 부르지 않는 방식은 0원이고,
        부르는 방식은 이 Provider가 답해야 한다. 단가를 모르면 amount를
        None으로 둔 채 돌려준다(0으로 채우지 않는다).
        """

        if not source_modes.calls_api(source_mode):
            return free_estimate(self.stage, self.name, source_mode)

        return CostEstimate(
            stage=self.stage, provider=self.name, source_mode=source_mode,
            amount=None, note="이 Provider가 아직 단가를 보고하지 않습니다.",
        )

    # ---- 사용 가능 여부 ----------------------------------------------

    def is_available(self) -> bool:
        """지금 설정으로 실제로 쓸 수 있는가.

        기본은 True다 - 자격증명이 필요한 Provider가 required_settings를
        선언하고 이 메서드를 재정의한다."""

        return True


def validate_capabilities(capabilities: ProviderCapabilities) -> ProviderCapabilities:
    """Provider가 스스로를 잘못 선언하는 것을 등록 시점에 잡는다."""

    stages.require_stage(capabilities.stage)

    if capabilities.quality_tier not in QUALITY_TIERS:
        raise ValueError(
            f"알 수 없는 품질 등급입니다: {capabilities.quality_tier!r}. "
            f"사용 가능한 값: {list(QUALITY_TIERS)}"
        )

    if not capabilities.supported_source_modes:
        raise ValueError(
            f"{capabilities.name}이(가) 지원하는 입력 방식이 하나도 없습니다."
        )

    for mode in capabilities.supported_source_modes:
        source_modes.require_source_mode(mode)

    return capabilities
