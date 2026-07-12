"""
Sprint96.1 (RED) - Hotfix: asset_quality_scorer의 asset_strategy override.

score_asset()에 optional 파라미터 asset_strategy=None을 추가한다. 기본값
(None/"default")은 기존 ASSET_TYPE_BASE_SCORE 그대로(video_frame=0.80 <
stock_image=0.85, Sprint30 이후 회귀 없음). asset_strategy="upload"일
때만 video_frame 점수를 stock_image + 0.01로 근소하게 우대한다(동점이
아니라 "아주 작은 우대" - tie-breaker/relevance에 밀리지 않도록). 아직
구현이 없으므로(RED) upload 관련 테스트는 실패해야 정상이다.
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_quality_scorer import score_asset


class TestScoreAssetUploadStrategy(unittest.TestCase):

    def test_default_video_frame_score_unchanged(self):
        candidate = {"source": "pixabay_video", "width": 1920, "height": 1080}
        self.assertAlmostEqual(score_asset(candidate), 0.80)

    def test_default_video_still_scores_lower_than_image(self):
        video = {"source": "pixabay_video", "width": 1920, "height": 1080}
        image = {"source": "pixabay_image", "width": 1920, "height": 1080}
        self.assertLess(score_asset(video), score_asset(image))

    def test_non_upload_asset_strategy_value_behaves_like_default(self):
        candidate = {"source": "pixabay_video", "width": 1920, "height": 1080}
        self.assertAlmostEqual(score_asset(candidate, asset_strategy="default"), 0.80)

    def test_upload_strategy_stock_image_score_unchanged(self):
        candidate = {"source": "pixabay_image", "width": 1920, "height": 1080}
        self.assertAlmostEqual(score_asset(candidate, asset_strategy="upload"), 0.85)

    def test_upload_strategy_ai_image_score_unchanged(self):
        candidate = {"source": "ai_image"}
        self.assertAlmostEqual(score_asset(candidate, asset_strategy="upload"), 0.95)

    def test_upload_strategy_video_frame_scores_point_zero_one_above_stock_image(self):
        video = {"source": "pixabay_video", "width": 1920, "height": 1080}
        image = {"source": "pixabay_image", "width": 1920, "height": 1080}

        video_score = score_asset(video, asset_strategy="upload")
        image_score = score_asset(image, asset_strategy="upload")

        self.assertAlmostEqual(video_score - image_score, 0.01)

    def test_upload_strategy_video_wins_over_image_when_otherwise_equal(self):
        video = {"source": "pixabay_video", "width": 1080, "height": 1920}
        image = {"source": "pixabay_image", "width": 1080, "height": 1920}

        self.assertGreater(
            score_asset(video, asset_strategy="upload"),
            score_asset(image, asset_strategy="upload"),
        )

    def test_upload_strategy_does_not_change_relevance_or_hook_bonus(self):
        portrait_video = {"source": "pixabay_video", "width": 1080, "height": 1920}
        landscape_video = {"source": "pixabay_video", "width": 1920, "height": 1080}

        self.assertAlmostEqual(
            score_asset(portrait_video, asset_strategy="upload")
            - score_asset(landscape_video, asset_strategy="upload"),
            0.05,
        )


if __name__ == "__main__":
    unittest.main()
