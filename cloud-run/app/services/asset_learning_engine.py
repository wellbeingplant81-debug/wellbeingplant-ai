from app.services.asset_feedback_service import load_all

SUCCESS_BONUS_PER_EVENT = 0.01
MAX_SUCCESS_BONUS = 0.05

FALLBACK_BONUS_PER_EVENT = 0.01
MAX_FALLBACK_BONUS = 0.05

FAILURE_PENALTY = 0.03
MIN_SAMPLE_SIZE_FOR_PENALTY = 5


def compute_bias(records: list, provider: str) -> float:
    """
    순수 함수 - 주어진 feedback 레코드만으로 provider의 학습된 bias를
    계산합니다 (파일 접근 없음, 완전히 결정적).

    학습 규칙:
    - provider == "ai_image": fallback 이벤트 횟수에 비례해 소폭
      가산(최대 MAX_FALLBACK_BONUS) - "fallback_to_ai면 ai_weight에
      small_bonus를 더한다".
    - 그 외 provider: 해당 provider의 success 이벤트 횟수에 비례해
      소폭 가산(최대 MAX_SUCCESS_BONUS) - "asset_used_successfully면
      provider_weight에 small_bonus를 더한다".
    - 전체 이력이 MIN_SAMPLE_SIZE_FOR_PENALTY개 이상 쌓였는데 해당
      provider가 단 한 번도 success한 적이 없으면 페널티를 뺀다 -
      "repeated failure면 provider_weight에서 penalty를 뺀다".
    """

    if not records:
        return 0.0

    if provider == "ai_image":
        fallback_count = sum(
            1 for r in records if r.get("outcome") == "fallback"
        )
        return min(fallback_count * FALLBACK_BONUS_PER_EVENT, MAX_FALLBACK_BONUS)

    provider_records = [r for r in records if r.get("provider") == provider]
    success_count = sum(
        1 for r in provider_records if r.get("outcome") == "success"
    )

    bonus = min(success_count * SUCCESS_BONUS_PER_EVENT, MAX_SUCCESS_BONUS)

    if len(records) >= MIN_SAMPLE_SIZE_FOR_PENALTY and success_count == 0:
        return bonus - FAILURE_PENALTY

    return bonus


def get_learned_bias(provider: str) -> float:
    """asset_feedback_service에 저장된 전체 이력을 로드해 bias를 계산합니다."""

    return compute_bias(load_all(), provider)
