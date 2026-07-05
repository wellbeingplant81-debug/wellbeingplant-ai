ASSET_TYPE_BASE_SCORE = {
    "ai_image": 0.95,
    "stock_image": 0.85,
    "video_frame": 0.80,
}

PROVIDER_WEIGHTS = {
    "pexels_image": 0.02,
    "pexels_video": 0.02,
    "pixabay_image": 0.0,
    "pixabay_video": 0.0,
    "ai_image": 0.0,
}

HOOK_SCENE_BONUS = 0.1

# 후보 데이터에는 태그/설명 등 의미적 메타데이터가 없어(Sprint28
# 설계 문서의 열린 이슈), 실제로 계산 가능한 신호인 세로 비율
# 일치 여부만 relevance 지표로 사용합니다.
PORTRAIT_RELEVANCE_BONUS = 0.05


def resolve_asset_type(source: str) -> str:
    """provider source 문자열을 스코어링용 asset_type으로 변환합니다."""

    if source == "ai_image":
        return "ai_image"

    if "video" in source:
        return "video_frame"

    return "stock_image"


def _relevance_score(candidate: dict) -> float:

    width = candidate.get("width")
    height = candidate.get("height")

    if not width or not height:
        return 0.0

    return PORTRAIT_RELEVANCE_BONUS if height > width else 0.0


def score_asset(
    candidate: dict,
    is_hook_scene: bool = False,
    learned_bias: float = 0.0,
) -> float:
    """
    후보 자산 하나의 점수를 계산합니다. 순수 함수입니다 - feedback
    파일 등 외부 상태를 직접 읽지 않고, 학습된 bias는 호출자가
    (asset_ranking_service.py를 통해) 명시적으로 전달합니다. 이는
    "deterministic scoring 유지" 요구사항을 만족시키기 위함이며,
    learned_bias의 기본값 0.0은 Sprint30 이전 동작과 완전히
    동일합니다.

    score = asset_type 기본 점수(confidence 역할: ai_image=0.95,
            stock_image=0.85, video_frame=0.80)
          + relevance(세로 비율 가산점, 최대 0.05)
          + provider 가중치(현재는 Pexels에 소폭 가산)
          + hook scene 보너스(scene 1이면 +0.1)
          + learned_bias(Sprint31 Learning Layer - 기본값 0.0)
    """

    source = candidate["source"]
    asset_type = resolve_asset_type(source)

    base = ASSET_TYPE_BASE_SCORE[asset_type]
    relevance = _relevance_score(candidate)
    provider_weight = PROVIDER_WEIGHTS.get(source, 0.0)
    hook_bonus = HOOK_SCENE_BONUS if is_hook_scene else 0.0

    return base + relevance + provider_weight + hook_bonus + learned_bias
