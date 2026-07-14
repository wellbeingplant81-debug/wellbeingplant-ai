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

# Sprint96.1 Hotfix - upload profile에서만 video_frame이 stock_image보다
# 아주 근소하게 우대되도록 하는 가산치("Video First"가 아니라 "Video
# Slight Preference"). 동점(0.85 == 0.85)으로 두면 relevance/hook 보너스가
# 이미지에도 똑같이 붙어 여전히 이미지가 반복 선택될 수 있어, 우대분을
# 명시적으로 더한다.
UPLOAD_VIDEO_PREFERENCE_BONUS = 0.01

# Sprint100-3 - Stock Video Intelligence. UPLOAD_VIDEO_PREFERENCE_BONUS
# (0.01)는 동점 tie-breaker일 뿐이라 stock_image 기본 점수(0.85)를
# 이기지 못한다(video_frame 0.80+0.01=0.81 < 0.85) - Production QA에서
# Pexels Video가 한 번도 선택되지 않은 근본 원인 중 하나. 호출자(scene
# 텍스트를 UploadAssetStrategy.prefers_video()로 판단한 asset_
# integration_service/step02_assets)가 이 scene은 실사 촬영이 자연스러운
# "Scene Intent"라고 명시적으로 표시(prefer_video=True)했을 때만, 최악의
# 경우(video landscape/무관련성 vs image portrait/최대 관련성)에도 항상
# video가 이기도록 결정적인 가산치를 더한다.
SCENE_INTENT_VIDEO_BONUS = 0.15

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
    asset_strategy: str = None,
    prefer_video: bool = False,
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

    Sprint96.1 Hotfix - asset_strategy="upload"일 때만 video_frame의
    기본 점수를 stock_image + UPLOAD_VIDEO_PREFERENCE_BONUS로 근소하게
    올린다. ASSET_TYPE_BASE_SCORE 테이블 자체는 건드리지 않으므로
    asset_strategy가 없거나 "upload"가 아니면 기존과 완전히 동일하다.

    Sprint100-3 Stock Video Intelligence - prefer_video=True(호출자가
    scene 텍스트로 이미 "이 scene은 실사 촬영이 어울린다"고 판단했을
    때만 명시)면 SCENE_INTENT_VIDEO_BONUS를 추가로 더해, 관련성/hook
    보너스 조건이 같다면 video_frame이 stock_image를 항상 이기게
    한다. prefer_video 기본값 False는 기존과 완전히 동일하다.
    """

    source = candidate["source"]
    asset_type = resolve_asset_type(source)

    if asset_strategy == "upload" and asset_type == "video_frame":
        base = ASSET_TYPE_BASE_SCORE["stock_image"] + UPLOAD_VIDEO_PREFERENCE_BONUS
    else:
        base = ASSET_TYPE_BASE_SCORE[asset_type]

    relevance = _relevance_score(candidate)
    provider_weight = PROVIDER_WEIGHTS.get(source, 0.0)
    hook_bonus = HOOK_SCENE_BONUS if is_hook_scene else 0.0
    scene_intent_bonus = (
        SCENE_INTENT_VIDEO_BONUS
        if asset_strategy == "upload" and prefer_video and asset_type == "video_frame"
        else 0.0
    )

    return (
        base + relevance + provider_weight + hook_bonus
        + scene_intent_bonus + learned_bias
    )
