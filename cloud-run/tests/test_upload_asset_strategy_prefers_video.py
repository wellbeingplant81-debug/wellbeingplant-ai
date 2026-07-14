"""
Sprint100-3 - UploadAssetStrategy.prefers_video(): 기존 STOCK_PRIORITY_
KEYWORDS(병원/의사/환자/운동/산책/식사/음식/일상생활 - 실사 촬영이 자연
스러운 "real world" scene들)를 Stock Video 우선 신호로도 재사용한다.
AI 우선 키워드(장기/혈관 등 의학 설명)에는 절대 적용되지 않는다.

추가로 '걷기'/'생활습관'/'풍경'/'자연' 키워드를 새로 인식한다 - 기존
키워드(산책/일상생활)와 유사하지만 실제 스크립트 narration에서 흔히
쓰이는 동의어라 커버리지가 빠져 있었다.
"""

import unittest

from app.services.upload_asset_strategy import UploadAssetStrategy


class TestUploadAssetStrategyPrefersVideo(unittest.TestCase):

    def test_lifestyle_scene_prefers_video(self):
        scene_metadata = {"narration": "매일 30분씩 가벼운 산책을 해보세요."}
        self.assertTrue(
            UploadAssetStrategy.prefers_video(scene_metadata, profile="upload")
        )

    def test_hospital_scene_prefers_video(self):
        scene_metadata = {"narration": "병원에서 정기 검진을 받는 모습입니다."}
        self.assertTrue(
            UploadAssetStrategy.prefers_video(scene_metadata, profile="upload")
        )

    def test_new_walking_synonym_prefers_video(self):
        scene_metadata = {"narration": "가벼운 걷기부터 시작해 보세요."}
        self.assertTrue(
            UploadAssetStrategy.prefers_video(scene_metadata, profile="upload")
        )

    def test_new_lifestyle_habit_synonym_prefers_video(self):
        scene_metadata = {"narration": "생활습관을 바꾸는 것이 가장 중요합니다."}
        self.assertTrue(
            UploadAssetStrategy.prefers_video(scene_metadata, profile="upload")
        )

    def test_new_nature_keyword_prefers_video(self):
        scene_metadata = {"narration": "공원의 풍경을 바라보며 산책합니다."}
        self.assertTrue(
            UploadAssetStrategy.prefers_video(scene_metadata, profile="upload")
        )

    def test_medical_scene_does_not_prefer_video(self):
        scene_metadata = {"narration": "우리 몸의 혈관 구조를 살펴봅니다."}
        self.assertFalse(
            UploadAssetStrategy.prefers_video(scene_metadata, profile="upload")
        )

    def test_non_upload_profile_never_prefers_video(self):
        scene_metadata = {"narration": "매일 30분씩 걷는 습관을 만들어 보세요."}
        self.assertFalse(
            UploadAssetStrategy.prefers_video(scene_metadata, profile="default")
        )

    def test_unmatched_scene_does_not_prefer_video(self):
        scene_metadata = {"narration": "오늘의 주제를 시작하겠습니다."}
        self.assertFalse(
            UploadAssetStrategy.prefers_video(scene_metadata, profile="upload")
        )


if __name__ == "__main__":
    unittest.main()
