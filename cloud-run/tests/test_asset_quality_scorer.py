import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_quality_scorer import resolve_asset_type, score_asset


class TestResolveAssetType(unittest.TestCase):

    def test_ai_image(self):
        self.assertEqual(resolve_asset_type("ai_image"), "ai_image")

    def test_pexels_video_is_video_frame(self):
        self.assertEqual(resolve_asset_type("pexels_video"), "video_frame")

    def test_pixabay_video_is_video_frame(self):
        self.assertEqual(resolve_asset_type("pixabay_video"), "video_frame")

    def test_pexels_image_is_stock_image(self):
        self.assertEqual(resolve_asset_type("pexels_image"), "stock_image")

    def test_pixabay_image_is_stock_image(self):
        self.assertEqual(resolve_asset_type("pixabay_image"), "stock_image")


class TestScoreAsset(unittest.TestCase):

    def test_ai_image_base_score(self):
        candidate = {"source": "ai_image"}
        self.assertAlmostEqual(score_asset(candidate), 0.95)

    def test_stock_image_base_score_no_bonus(self):
        candidate = {"source": "pixabay_image", "width": 1920, "height": 1080}
        self.assertAlmostEqual(score_asset(candidate), 0.85)

    def test_video_frame_base_score_lower_than_image(self):
        image_score = score_asset({"source": "pixabay_image", "width": 1920, "height": 1080})
        video_score = score_asset({"source": "pixabay_video", "width": 1920, "height": 1080})
        self.assertLess(video_score, image_score)

    def test_portrait_orientation_adds_relevance_bonus(self):
        landscape = score_asset({"source": "pixabay_image", "width": 1920, "height": 1080})
        portrait = score_asset({"source": "pixabay_image", "width": 1080, "height": 1920})
        self.assertAlmostEqual(portrait - landscape, 0.05)

    def test_missing_dimensions_get_no_relevance_bonus(self):
        candidate = {"source": "pixabay_image"}
        self.assertAlmostEqual(score_asset(candidate), 0.85)

    def test_pexels_provider_weight_beats_pixabay_all_else_equal(self):
        pexels = score_asset({"source": "pexels_image", "width": 1080, "height": 1920})
        pixabay = score_asset({"source": "pixabay_image", "width": 1080, "height": 1920})
        self.assertGreater(pexels, pixabay)

    def test_hook_scene_adds_fixed_bonus(self):
        candidate = {"source": "ai_image"}
        without_bonus = score_asset(candidate, is_hook_scene=False)
        with_bonus = score_asset(candidate, is_hook_scene=True)
        self.assertAlmostEqual(with_bonus - without_bonus, 0.1)

    def test_default_learned_bias_is_zero_matches_sprint30_behavior(self):
        candidate = {"source": "pexels_image", "width": 1080, "height": 1920}
        self.assertAlmostEqual(
            score_asset(candidate),
            score_asset(candidate, learned_bias=0.0),
        )

    def test_learned_bias_is_added_directly_to_score(self):
        candidate = {"source": "ai_image"}
        base = score_asset(candidate)
        boosted = score_asset(candidate, learned_bias=0.2)
        self.assertAlmostEqual(boosted - base, 0.2)

    def test_negative_learned_bias_reduces_score(self):
        candidate = {"source": "ai_image"}
        base = score_asset(candidate)
        penalized = score_asset(candidate, learned_bias=-0.1)
        self.assertAlmostEqual(base - penalized, 0.1)


if __name__ == "__main__":
    unittest.main()
