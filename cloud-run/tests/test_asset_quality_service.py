import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_quality_service


SCENE = {
    "scene": 1,
    "narration": "tired woman resting quietly at home",
    "image_prompt": "a tired woman resting on a couch at home",
}


def _good_asset(local_path: str) -> dict:
    return {
        "source": "pexels_image",
        "local_path": local_path,
        "metadata": {
            "query": "tired woman resting",
            "width": 720,
            "height": 1280,
        },
    }


class TestScoreAsset(unittest.TestCase):

    def test_all_checks_pass_scores_100(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            asset = _good_asset(tmp_path)
            result = asset_quality_service.score_asset(SCENE, asset)

            self.assertEqual(result["score"], 100)
            self.assertTrue(result["passed"])
            self.assertEqual(result["reasons"], [])
        finally:
            os.remove(tmp_path)

    def test_missing_asset_and_forbidden_text_fails(self):
        asset = {
            "source": "pexels_image",
            "local_path": os.path.join(tempfile.gettempdir(), "does_not_exist.jpg"),
            "metadata": {
                "query": "watermark sample image",
                "width": 720,
                "height": 1280,
            },
        }

        result = asset_quality_service.score_asset(SCENE, asset)

        self.assertLess(result["score"], asset_quality_service.PASS_THRESHOLD)
        self.assertFalse(result["passed"])
        self.assertIn("asset_missing", result["reasons"])
        self.assertIn("forbidden_text_detected", result["reasons"])

    def test_threshold_just_below_80_fails(self):
        """asset_exists(21점)만 실패 -> 79점, PASS_THRESHOLD(80) 미만이라 FAIL."""

        asset = _good_asset(
            os.path.join(tempfile.gettempdir(), "does_not_exist.jpg")
        )

        result = asset_quality_service.score_asset(SCENE, asset)

        self.assertEqual(result["score"], 79)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reasons"], ["asset_missing"])

    def test_threshold_exactly_80_passes(self):
        """prompt_match(20점)만 실패 -> 80점, PASS_THRESHOLD(80) 이상이라 PASS."""

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            asset = _good_asset(tmp_path)
            scene = dict(SCENE, image_prompt="xyz completely unrelated zzz qqq")

            result = asset_quality_service.score_asset(scene, asset)

            self.assertEqual(result["score"], 80)
            self.assertTrue(result["passed"])
            self.assertEqual(result["reasons"], ["low_prompt_match"])
        finally:
            os.remove(tmp_path)

    def test_ai_image_source_always_passes_aspect_ratio(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            asset = {
                "source": "ai_image",
                "local_path": tmp_path,
                "metadata": {"query": "tired woman resting"},
            }

            result = asset_quality_service.score_asset(SCENE, asset)

            self.assertNotIn("aspect_ratio_mismatch", result["reasons"])
        finally:
            os.remove(tmp_path)

    def test_landscape_stock_asset_fails_aspect_ratio(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            asset = _good_asset(tmp_path)
            asset["metadata"]["width"] = 1280
            asset["metadata"]["height"] = 720

            result = asset_quality_service.score_asset(SCENE, asset)

            self.assertIn("aspect_ratio_mismatch", result["reasons"])
        finally:
            os.remove(tmp_path)

    def test_return_object_shape_and_types(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            asset = _good_asset(tmp_path)
            result = asset_quality_service.score_asset(SCENE, asset)

            self.assertEqual(set(result.keys()), {"score", "passed", "reasons"})
            self.assertIsInstance(result["score"], int)
            self.assertIsInstance(result["passed"], bool)
            self.assertIsInstance(result["reasons"], list)
            self.assertTrue(all(isinstance(r, str) for r in result["reasons"]))
        finally:
            os.remove(tmp_path)


class TestEvaluateAssetRegenerationIntegration(unittest.TestCase):

    def test_low_score_triggers_regeneration_engine(self):
        asset = {
            "source": "pexels_image",
            "local_path": os.path.join(tempfile.gettempdir(), "missing.jpg"),
            "metadata": {
                "query": "watermark sample image",
                "width": 720,
                "height": 1280,
            },
        }

        with patch.object(asset_quality_service.regeneration_service, "run") as mock_run:
            result = asset_quality_service.evaluate_asset(SCENE, asset, "/fake/project")

        self.assertFalse(result["passed"])
        mock_run.assert_called_once_with("/fake/project")

    def test_high_score_does_not_trigger_regeneration_engine(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            asset = _good_asset(tmp_path)

            with patch.object(asset_quality_service.regeneration_service, "run") as mock_run:
                result = asset_quality_service.evaluate_asset(SCENE, asset, "/fake/project")

            self.assertTrue(result["passed"])
            mock_run.assert_not_called()
        finally:
            os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
