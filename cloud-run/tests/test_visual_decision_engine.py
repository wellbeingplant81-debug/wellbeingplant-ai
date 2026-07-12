"""
Sprint90 (RED) - Visual Decision Engine Foundation 테스트.

VisualDecisionEngine.select_visual_mode(scene_metadata, profile="upload")는
scene 텍스트를 키워드로만 검사해 4가지 VisualMode
(AI_IMAGE/AI_VIDEO/STOCK_IMAGE/STOCK_VIDEO) 중 하나를 고른다.
profile="upload"일 때만 아래 규칙이 적용되고, 그 외 profile은 기존
Pipeline이 쓰는 기본값(STOCK_IMAGE)을 그대로 반환해야 한다. 아직
구현이 없으므로(RED) 모든 테스트는 실패해야 정상이다.
"""

import unittest

from app.services.visual_decision_engine import VisualDecisionEngine, VisualMode


class TestVisualDecisionEngine(unittest.TestCase):

    def test_medical_explanation_prefers_ai_image(self):
        scene_metadata = {"narration": "혈관과 신경이 어떻게 연결되는지 살펴보겠습니다."}
        result = VisualDecisionEngine.select_visual_mode(scene_metadata, profile="upload")
        self.assertEqual(result, VisualMode.AI_IMAGE)

    def test_movement_instruction_prefers_ai_video(self):
        scene_metadata = {"narration": "지금부터 어깨를 크게 돌리는 동작을 따라 해보세요."}
        result = VisualDecisionEngine.select_visual_mode(scene_metadata, profile="upload")
        self.assertEqual(result, VisualMode.AI_VIDEO)

    def test_real_world_scene_prefers_stock_video(self):
        scene_metadata = {"narration": "병원 대기실에 앉아있는 환자의 일상적인 모습입니다."}
        result = VisualDecisionEngine.select_visual_mode(scene_metadata, profile="upload")
        self.assertEqual(result, VisualMode.STOCK_VIDEO)

    def test_emotional_scene_prefers_ai_image(self):
        scene_metadata = {"narration": "안도감에 미소 짓는 표정이 얼굴에 번집니다."}
        result = VisualDecisionEngine.select_visual_mode(scene_metadata, profile="upload")
        self.assertEqual(result, VisualMode.AI_IMAGE)

    def test_default_returns_stock(self):
        scene_metadata = {"narration": "오늘의 주제를 시작하겠습니다."}
        result = VisualDecisionEngine.select_visual_mode(scene_metadata, profile="upload")
        self.assertEqual(result, VisualMode.STOCK_IMAGE)

    def test_existing_pipeline_unchanged(self):
        scene_metadata = {"narration": "혈관과 신경이 어떻게 연결되는지 살펴보겠습니다."}
        result = VisualDecisionEngine.select_visual_mode(scene_metadata, profile="development")
        self.assertEqual(result, VisualMode.STOCK_IMAGE)


if __name__ == "__main__":
    unittest.main()
