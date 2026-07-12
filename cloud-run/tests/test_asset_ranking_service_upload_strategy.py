"""
Sprint96.1 (RED) - Hotfix: asset_ranking_service의 asset_strategy 전달.

select_best()/select_best_with_score()에 optional 파라미터
asset_strategy=None을 추가해 score_asset()에 그대로 전달한다. 기본값은
기존 동작(video가 image에 짐) 그대로이고, asset_strategy="upload"일 때만
동일 조건에서 video가 이긴다. 아직 구현이 없으므로(RED) upload 관련
테스트는 실패해야 정상이다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_ranking_service import select_best, select_best_with_score


class TestSelectBestUploadStrategy(unittest.TestCase):

    def setUp(self):
        patcher = patch(
            "app.services.asset_ranking_service.load_all",
            return_value=[],
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_default_video_still_loses_to_image(self):
        video = {"source": "pexels_video", "width": 1080, "height": 1920}
        image = {"source": "pixabay_image", "width": 1080, "height": 1920}

        self.assertEqual(select_best([video, image]), image)

    def test_upload_strategy_video_wins_over_image_when_otherwise_equal(self):
        video = {"source": "pexels_video", "width": 1080, "height": 1920}
        image = {"source": "pexels_image", "width": 1080, "height": 1920}

        result = select_best([video, image], asset_strategy="upload")

        self.assertEqual(result["source"], "pexels_video")

    def test_select_best_with_score_returns_video_winner_with_upload_strategy(self):
        video = {"source": "pexels_video", "width": 1080, "height": 1920}
        image = {"source": "pexels_image", "width": 1080, "height": 1920}

        candidate, score = select_best_with_score([video, image], asset_strategy="upload")

        self.assertEqual(candidate["source"], "pexels_video")
        self.assertIsNotNone(score)


if __name__ == "__main__":
    unittest.main()
