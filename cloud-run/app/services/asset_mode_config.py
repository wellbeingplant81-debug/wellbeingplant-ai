"""
Sprint38 - Hybrid Asset Engine의 ASSET_MODE 설정.

각 모드는 두 값을 함께 정의한다:
  - ai_ratio_cap: scene 배치 전체에서 "AI 우선 품질 게이트" 대상으로
    삼을 scene 수의 상한 비율 (강제 목표가 아니라 상한).
  - pexels_quality_threshold: AI 우선 후보 scene에서도, 검색된 Pexels/
    Pixabay 후보의 점수(asset_quality_scorer.score_asset)가 이 값
    이상이면 비용보다 품질을 우선해 그대로 Pexels를 채택한다.

premium은 두 값 모두 가장 까다로워(더 많은 scene을 AI 후보로 삼고,
Pexels를 채택하는 기준도 높아) 결과적으로 AI 사용이 늘고, low_cost는
반대로 AI 후보를 줄이고 웬만한 Pexels 품질도 통과시켜 비용을 아낀다.
"""

import os

ASSET_MODE_CONFIG = {
    "low_cost": {
        "ai_ratio_cap": 0.20,
        "pexels_quality_threshold": 0.85,
    },
    "balanced": {
        "ai_ratio_cap": 0.30,
        "pexels_quality_threshold": 0.90,
    },
    "premium": {
        "ai_ratio_cap": 0.60,
        "pexels_quality_threshold": 0.95,
    },
}

DEFAULT_MODE = "balanced"


def get_asset_mode() -> str:
    """
    ASSET_MODE 환경변수를 읽어 유효한 모드 이름을 반환합니다. 미설정/
    알 수 없는 값이면 조용히 DEFAULT_MODE로 대체합니다 - 잘못된 값
    하나 때문에 파이프라인이 죽어서는 안 됩니다.
    """

    mode = os.getenv("ASSET_MODE", DEFAULT_MODE).lower()

    return mode if mode in ASSET_MODE_CONFIG else DEFAULT_MODE


def _resolve_mode(mode: str = None) -> str:

    if mode is None:
        mode = get_asset_mode()

    return mode if mode in ASSET_MODE_CONFIG else DEFAULT_MODE


def get_ai_ratio_cap(mode: str = None) -> float:
    return ASSET_MODE_CONFIG[_resolve_mode(mode)]["ai_ratio_cap"]


def get_pexels_quality_threshold(mode: str = None) -> float:
    return ASSET_MODE_CONFIG[_resolve_mode(mode)]["pexels_quality_threshold"]
