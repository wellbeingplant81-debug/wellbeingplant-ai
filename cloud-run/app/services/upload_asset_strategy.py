"""
Sprint88 (GREEN) - Upload Asset Strategy v1.

업로드용(Production) Asset Strategy. scene_metadata의 텍스트를 키워드로만
검사해 AI 생성 이미지를 쓸지 Stock(Pexels/Pixabay) 이미지를 쓸지 정한다.
profile="upload"일 때만 아래 키워드 규칙이 적용되고, 그 외 profile은
기존 기본값(STOCK)을 그대로 반환한다 - Hybrid Asset Engine/Planner/
Pipeline은 전혀 건드리지 않는다.
"""

from enum import Enum


class AssetMode(str, Enum):
    AI = "ai"
    STOCK = "stock"


DEFAULT_PROFILE = "upload"

# 업로드 프로파일 - AI 우선 키워드 (카테고리별 1개씩)
AI_PRIORITY_KEYWORDS = {
    "medical_visual": ["암세포"],
    "internal_organs": ["장기"],
    "blood_vessels": ["혈관"],
    "brain": ["뇌"],
    "nerves": ["신경"],
    "inflammation": ["염증"],
    "disease_progress": ["질병 진행"],
    "anatomy": ["내부 구조"],
}

# 업로드 프로파일 - Stock 우선 키워드 (카테고리별로 여러 동의어 가능)
STOCK_PRIORITY_KEYWORDS = {
    "doctor": ["의사"],
    "hospital": ["병원"],
    "patient": ["환자"],
    "exercise": ["운동"],
    "walking": ["산책", "걷기"],
    "meal": ["식사"],
    "food": ["음식"],
    "lifestyle": ["일상생활", "생활습관"],
    "nature": ["풍경", "자연"],
}


def _flatten(keyword_groups: dict) -> list:
    return [keyword for keywords in keyword_groups.values() for keyword in keywords]


def _extract_text(scene_metadata) -> str:

    if isinstance(scene_metadata, str):
        return scene_metadata

    if isinstance(scene_metadata, dict):
        return " ".join(value for value in scene_metadata.values() if isinstance(value, str))

    return ""


class UploadAssetStrategy:

    @staticmethod
    def select_asset_mode(scene_metadata, profile=DEFAULT_PROFILE):

        if profile != "upload":
            return AssetMode.STOCK

        text = _extract_text(scene_metadata)

        if any(keyword in text for keyword in _flatten(AI_PRIORITY_KEYWORDS)):
            return AssetMode.AI

        return AssetMode.STOCK

    @staticmethod
    def prefers_video(scene_metadata, profile=DEFAULT_PROFILE) -> bool:
        """
        Sprint100-3 - Stock Video Intelligence. STOCK_PRIORITY_KEYWORDS
        (병원/의사/환자/운동/걷기/식사/음식/생활습관/풍경 - 실사 촬영이
        자연스러운 "real world" scene)에 해당하면 Stock Video를 Stock
        Image보다 우선하도록 True를 반환한다. profile != "upload"이거나
        AI 우선(의학 설명) scene이면 항상 False - Scene Intent 판단은
        select_asset_mode()와 동일한 텍스트/키워드 규칙을 재사용한다.
        """

        if profile != "upload":
            return False

        text = _extract_text(scene_metadata)

        return any(keyword in text for keyword in _flatten(STOCK_PRIORITY_KEYWORDS))
