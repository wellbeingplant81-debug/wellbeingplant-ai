"""
Sprint92 (GREEN) - Visual Decision Integration v1.

Pipeline이 VisualDecisionEngine을 호출할지 말지 결정하는 Feature Flag
진입점. enabled=False(기본값)면 VisualDecisionEngine을 전혀 호출하지
않고 항상 VisualMode.STOCK_IMAGE를 반환해 기존 Pipeline 동작을 그대로
유지하고, enabled=True일 때만 VisualDecisionEngine.select_visual_mode()를
호출해 그 반환값을 그대로 돌려준다.
"""

from app.services.visual_decision_engine import VisualDecisionEngine, VisualMode


class VisualDecisionIntegration:

    @staticmethod
    def select_mode(scene_metadata, profile="development", enabled=False):

        if not enabled:
            return VisualMode.STOCK_IMAGE

        return VisualDecisionEngine.select_visual_mode(scene_metadata, profile)
