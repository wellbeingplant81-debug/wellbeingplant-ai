"""
Sprint88 (RED) - Upload Asset Strategy 테스트.

업로드용(Production) Asset Strategy는 scene_metadata(narration 등 scene
텍스트)를 보고 AI 생성 이미지를 쓸지 Stock(Pexels/Pixabay) 이미지를
쓸지 결정한다. profile="upload"일 때만 아래 규칙이 적용된다:
  - 장기/혈관/뇌/신경/암세포/염증/질병 진행/내부 구조 키워드 -> "ai"
  - 병원/의사/환자/식사/운동/산책/일상생활 키워드 -> "stock"
"upload"가 아닌 기존 profile은 이 규칙의 영향을 받지 않아야 한다.
아직 구현이 없으므로(RED) 모든 테스트는 실패해야 정상이다.
"""

import unittest

from app.services.upload_asset_strategy import UploadAssetStrategy


class TestUploadAssetStrategy(unittest.TestCase):

    def test_medical_visual_prefers_ai(self):
        scene_metadata = {"narration": "우리 몸의 장기는 서로 연결되어 있습니다."}
        result = UploadAssetStrategy.select_asset_mode(scene_metadata, profile="upload")
        self.assertEqual(result, "ai")

    def test_internal_organs_prefers_ai(self):
        scene_metadata = {"narration": "몸속 내부 구조를 살펴보겠습니다."}
        result = UploadAssetStrategy.select_asset_mode(scene_metadata, profile="upload")
        self.assertEqual(result, "ai")

    def test_disease_progress_prefers_ai(self):
        scene_metadata = {"narration": "이 질병 진행 과정을 단계별로 보여드립니다."}
        result = UploadAssetStrategy.select_asset_mode(scene_metadata, profile="upload")
        self.assertEqual(result, "ai")

    def test_real_world_scene_prefers_stock(self):
        scene_metadata = {"narration": "병원에서 의사와 상담하는 환자의 모습입니다."}
        result = UploadAssetStrategy.select_asset_mode(scene_metadata, profile="upload")
        self.assertEqual(result, "stock")

    def test_upload_profile_defaults(self):
        scene_metadata = {"narration": "혈관 건강을 지키는 습관을 알아봅니다."}
        result = UploadAssetStrategy.select_asset_mode(scene_metadata)
        self.assertEqual(result, "ai")

    def test_existing_profile_unchanged(self):
        scene_metadata = {"narration": "혈관 건강을 지키는 습관을 알아봅니다."}
        result = UploadAssetStrategy.select_asset_mode(scene_metadata, profile="default")
        self.assertEqual(result, "stock")


if __name__ == "__main__":
    unittest.main()
