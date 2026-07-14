"""
Sprint100-3 - select_best()/select_best_with_score()가 prefer_video를
score_asset()에 그대로 전달하는지 확인한다. [[test_asset_quality_scorer_scene_intent_video]] 참고.
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


class TestSelectBestSceneIntentVideo(unittest.TestCase):

    def setUp(self):
        patcher = patch(
            "app.services.asset_ranking_service.load_all",
            return_value=[],
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_prefer_video_flips_selection_toward_video(self):
        video = {"source": "pexels_video", "width": 1920, "height": 1080}
        image = {"source": "pexels_image", "width": 1080, "height": 1920}

        result = select_best(
            [video, image], asset_strategy="upload", prefer_video=True,
        )

        self.assertEqual(result["source"], "pexels_video")

    def test_prefer_video_default_false_keeps_image_winning(self):
        video = {"source": "pexels_video", "width": 1920, "height": 1080}
        image = {"source": "pexels_image", "width": 1080, "height": 1920}

        result = select_best([video, image], asset_strategy="upload")

        self.assertEqual(result["source"], "pexels_image")

    def test_select_best_with_score_forwards_prefer_video(self):
        video = {"source": "pexels_video", "width": 1920, "height": 1080}
        image = {"source": "pexels_image", "width": 1080, "height": 1920}

        candidate, score = select_best_with_score(
            [video, image], asset_strategy="upload", prefer_video=True,
        )

        self.assertEqual(candidate["source"], "pexels_video")
        self.assertIsNotNone(score)


if __name__ == "__main__":
    unittest.main()
