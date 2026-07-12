"""
Sprint90 (GREEN) - Visual Decision Engine v1.

scene_metadata의 텍스트를 키워드로만 검사해 4가지 VisualMode
(AI_IMAGE/AI_VIDEO/STOCK_IMAGE/STOCK_VIDEO) 중 하나를 고른다.
profile="upload"일 때만 아래 키워드 규칙이 적용되고, 그 외 profile은
기존 Pipeline 기본값(STOCK_IMAGE)을 그대로 반환한다 - Pipeline/
UploadAssetStrategy/ProductionProfile/Planner는 전혀 건드리지 않는다.
"""

from enum import Enum


class VisualMode(Enum):
    AI_IMAGE = "ai_image"
    AI_VIDEO = "ai_video"
    STOCK_IMAGE = "stock_image"
    STOCK_VIDEO = "stock_video"


DEFAULT_MODE = VisualMode.STOCK_IMAGE

# (카테고리, 키워드, 모드) 순서대로 검사해 먼저 매칭되는 규칙 하나만 적용한다.
VISUAL_MODE_RULES = [
    ("medical_explanation", ["혈관", "신경"], VisualMode.AI_IMAGE),
    ("movement_instruction", ["동작"], VisualMode.AI_VIDEO),
    ("real_world_scene", ["병원", "일상"], VisualMode.STOCK_VIDEO),
    ("emotional_scene", ["표정", "미소", "안도감"], VisualMode.AI_IMAGE),
]


def _extract_text(scene_metadata) -> str:

    if isinstance(scene_metadata, str):
        return scene_metadata

    if isinstance(scene_metadata, dict):
        return " ".join(value for value in scene_metadata.values() if isinstance(value, str))

    return ""


class VisualDecisionEngine:

    @staticmethod
    def select_visual_mode(scene_metadata, profile="upload"):

        if profile != "upload":
            return DEFAULT_MODE

        text = _extract_text(scene_metadata)

        for _category, keywords, mode in VISUAL_MODE_RULES:
            if any(keyword in text for keyword in keywords):
                return mode

        return DEFAULT_MODE
