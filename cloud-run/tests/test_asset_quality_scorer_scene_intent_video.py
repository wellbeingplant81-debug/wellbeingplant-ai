"""
Sprint100-3 - Stock Video Intelligence: Scene Intent 기반 Video 우대.

Sprint96.1의 asset_strategy="upload" 근소 우대(+0.01)는 tie-breaker일
뿐이라, 실제로는 stock_image(0.85) 기본 점수가 video_frame(0.80)보다
항상 높아 video가 선택되지 않는다(Production QA에서 Pexels Video=0으로
확인됨). 이 스프린트는 "단순 점수 조정"이 아니라 "Scene Intent 기반"
결정을 추가한다: 호출자(asset_integration_service -> step02_assets가
UploadAssetStrategy.prefers_video()로 scene 텍스트를 보고 판단)가
prefer_video=True를 명시적으로 줄 때만, video_frame이 관련성/hook
보너스가 동일해도 stock_image를 확실히 이기도록 결정적인 가산치를
더한다. prefer_video=False(기본값)면 기존 동작(Sprint96.1의 근소
우대까지 포함)과 완전히 동일하다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_quality_scorer import score_asset


class TestSceneIntentVideoPreference(unittest.TestCase):

    def test_prefer_video_false_by_default_unchanged(self):
        candidate = {"source": "pixabay_video", "width": 1920, "height": 1080}
        # Sprint96.1의 근소 우대(stock_image base 0.85 + 0.01)만 적용된
        # 값 - Sprint100-3의 SCENE_INTENT_VIDEO_BONUS는 아직 붙지 않는다.
        self.assertAlmostEqual(score_asset(candidate, asset_strategy="upload"), 0.86)

    def test_prefer_video_true_video_beats_image_even_in_worst_case(self):
        # video는 landscape(관련성 보너스 없음), image는 portrait(최대
        # 관련성 보너스) - video에 가장 불리한 조건에서도 이겨야 한다.
        video = {"source": "pixabay_video", "width": 1920, "height": 1080}
        image = {"source": "pixabay_image", "width": 1080, "height": 1920}

        video_score = score_asset(video, asset_strategy="upload", prefer_video=True)
        image_score = score_asset(image, asset_strategy="upload", prefer_video=True)

        self.assertGreater(video_score, image_score)

    def test_prefer_video_true_without_upload_strategy_has_no_effect(self):
        # prefer_video는 asset_strategy="upload"가 아닌 호출부에서는
        # 절대 True로 넘어오지 않는 것이 계약이지만, 방어적으로 그런
        # 경우가 와도 기존 기본 점수(Sprint30)에서 벗어나지 않는다.
        candidate = {"source": "pixabay_video", "width": 1920, "height": 1080}
        self.assertAlmostEqual(score_asset(candidate, prefer_video=True), 0.80)

    def test_prefer_video_does_not_affect_image_or_ai_scores(self):
        image = {"source": "pixabay_image", "width": 1920, "height": 1080}
        ai = {"source": "ai_image"}

        self.assertAlmostEqual(
            score_asset(image, asset_strategy="upload", prefer_video=True),
            score_asset(image, asset_strategy="upload", prefer_video=False),
        )
        self.assertAlmostEqual(
            score_asset(ai, asset_strategy="upload", prefer_video=True),
            score_asset(ai, asset_strategy="upload", prefer_video=False),
        )


if __name__ == "__main__":
    unittest.main()
