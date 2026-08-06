"""
Sprint102 - 비용 인터페이스 (Epic 54, Architecture Phase 1).

영상을 만들기 전에 얼마가 들지 알 수 있어야 한다. 이번 스프린트는
그 계산을 하지 않는다 - 계산 결과가 담길 모양과, Provider가 답해야 할
질문만 정한다.

숫자를 지어내지 않는다. Provider가 자기 단가를 모르면 unknown으로
남긴다 - 0으로 채우면 "공짜"라는 거짓말이 되고, 임의의 값을 넣으면
그것이 근거처럼 보인다. 이 저장소에서 반복된 사고가 그런 종류였다.

단위는 Provider마다 다르다(대본은 1회, 이미지는 장수, 음성은 글자
수). 그래서 CostEstimate는 amount와 unit을 함께 담고, 합산은 통화
기준으로만 한다.
"""

from dataclasses import dataclass, field
from typing import List, Optional

USD = "USD"

# 단가를 모르는 Provider가 쓰는 값. None과 구분한다 - None은 "아직
# 물어보지 않았다", UNKNOWN은 "물어봤는데 모른다"이다.
UNKNOWN = "unknown"


@dataclass(frozen=True)
class CostEstimate:
    """한 단계의 예상 비용."""

    stage: str
    provider: str
    source_mode: str
    # 모르면 None. 0.0과 다르다 - 0.0은 "무료임을 안다"이다.
    amount: Optional[float] = None
    currency: str = USD
    # 무엇을 몇 개 쓰는지(이미지 6장, 문자 900자). 화면이 근거를
    # 보여줄 수 있게 담아 둔다.
    unit: str = ""
    quantity: Optional[float] = None
    note: str = ""

    @property
    def known(self) -> bool:
        return self.amount is not None

    @property
    def free(self) -> bool:
        return self.amount == 0.0


@dataclass
class CostBreakdown:
    """영상 하나의 예상 비용. 단계별 내역을 그대로 들고 있는다."""

    estimates: List[CostEstimate] = field(default_factory=list)

    def add(self, estimate: CostEstimate) -> None:
        self.estimates.append(estimate)

    @property
    def known_total(self) -> float:
        """알고 있는 것만 더한다."""

        return sum(e.amount for e in self.estimates if e.known)

    @property
    def unknown_stages(self) -> List[str]:
        """단가를 모르는 단계. 화면은 이것을 숨기지 말아야 한다 -
        "총 $0.30"이라고만 쓰면 모르는 항목이 0으로 보인다."""

        return [e.stage for e in self.estimates if not e.known]

    @property
    def complete(self) -> bool:
        return not self.unknown_stages

    def as_dict(self) -> dict:
        return {
            "known_total": round(self.known_total, 6),
            "currency": USD,
            "complete": self.complete,
            "unknown_stages": self.unknown_stages,
            "estimates": [
                {
                    "stage": e.stage,
                    "provider": e.provider,
                    "source_mode": e.source_mode,
                    "amount": e.amount,
                    "unit": e.unit,
                    "quantity": e.quantity,
                    "note": e.note,
                }
                for e in self.estimates
            ],
        }


def free_estimate(stage: str, provider: str, source_mode: str,
                  note: str = "") -> CostEstimate:
    """API를 부르지 않는 방식(IMPORT/MANUAL)의 비용은 0이다.

    이것은 추측이 아니라 정의다 - 우리가 아무 API도 부르지 않으므로
    우리에게 청구되는 금액이 없다. 사용자가 ChatGPT 구독료를 내고
    있는지는 우리가 알 수도, 청구할 수도 없는 일이다."""

    return CostEstimate(
        stage=stage, provider=provider, source_mode=source_mode,
        amount=0.0, note=note or "API를 호출하지 않습니다.",
    )
