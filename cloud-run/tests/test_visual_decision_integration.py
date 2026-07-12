"""
Sprint92 (RED) - Visual Decision Integration Foundation 테스트.

VisualDecisionIntegration.select_mode(scene_metadata, profile="development",
enabled=False)는 Pipeline이 VisualDecisionEngine을 호출할지 말지 결정하는
Feature Flag 진입점이다. enabled=False(기본값)이면 VisualDecisionEngine을
전혀 호출하지 않고 항상 VisualMode.STOCK_IMAGE를 반환해 기존 Pipeline
동작과 동일하게 유지한다. enabled=True일 때만
VisualDecisionEngine.select_visual_mode(scene_metadata, profile)를 호출해
그 반환값을 그대로 돌려준다. 아직 구현이 없으므로(RED) 모든 테스트는
실패해야 정상이다.
"""

import unittest

from app.services.visual_decision_engine import VisualMode
from app.services.visual_decision_integration import VisualDecisionIntegration


class TestVisualDecisionIntegration(unittest.TestCase):

    def test_default_returns_stock_image(self):
        scene_metadata = {"narration": "혈관과 신경이 어떻게 연결되는지 살펴보겠습니다."}
        result = VisualDecisionIntegration.select_mode(scene_metadata)
        self.assertEqual(result, VisualMode.STOCK_IMAGE)

    def test_feature_flag_default_off(self):
        scene_metadata = {"narration": "혈관과 신경이 어떻게 연결되는지 살펴보겠습니다."}
        result = VisualDecisionIntegration.select_mode(scene_metadata, profile="upload")
        self.assertEqual(result, VisualMode.STOCK_IMAGE)

    def test_enabled_calls_visual_engine(self):
        scene_metadata = {"narration": "혈관과 신경이 어떻게 연결되는지 살펴보겠습니다."}
        result = VisualDecisionIntegration.select_mode(scene_metadata, profile="upload", enabled=True)
        self.assertEqual(result, VisualMode.AI_IMAGE)

    def test_upload_profile_uses_visual_engine(self):
        scene_metadata = {"narration": "지금부터 어깨를 크게 돌리는 동작을 따라 해보세요."}
        result = VisualDecisionIntegration.select_mode(scene_metadata, profile="upload", enabled=True)
        self.assertEqual(result, VisualMode.AI_VIDEO)

    def test_development_profile_preserves_existing_behavior(self):
        scene_metadata = {"narration": "혈관과 신경이 어떻게 연결되는지 살펴보겠습니다."}
        result = VisualDecisionIntegration.select_mode(scene_metadata, profile="development", enabled=True)
        self.assertEqual(result, VisualMode.STOCK_IMAGE)

    def test_existing_pipeline_path_unchanged(self):
        scene_metadata = {"narration": "지금부터 어깨를 크게 돌리는 동작을 따라 해보세요."}
        result = VisualDecisionIntegration.select_mode(scene_metadata)
        self.assertEqual(result, VisualMode.STOCK_IMAGE)


if __name__ == "__main__":
    unittest.main()
