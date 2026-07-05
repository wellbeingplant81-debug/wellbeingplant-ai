import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_feedback_service


class TestAssetFeedbackService(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.feedback_path = os.path.join(self._tmp_dir.name, "feedback.json")

    def test_load_all_returns_empty_list_when_file_missing(self):
        self.assertEqual(asset_feedback_service.load_all(self.feedback_path), [])

    def test_record_persists_entry_to_disk(self):
        asset_feedback_service.record(
            scene_id=1,
            provider="pexels_image",
            asset_type="image",
            selected_asset="images/scene1.png",
            outcome="success",
            feedback_path=self.feedback_path,
        )

        records = asset_feedback_service.load_all(self.feedback_path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["scene_id"], 1)
        self.assertEqual(records[0]["provider"], "pexels_image")
        self.assertEqual(records[0]["asset_type"], "image")
        self.assertEqual(records[0]["selected_asset"], "images/scene1.png")
        self.assertEqual(records[0]["outcome"], "success")
        self.assertIn("timestamp", records[0])

    def test_multiple_records_accumulate(self):
        for i in range(3):
            asset_feedback_service.record(
                scene_id=i,
                provider="ai_image",
                asset_type="image",
                selected_asset=f"images/scene{i}.png",
                outcome="fallback",
                feedback_path=self.feedback_path,
            )

        records = asset_feedback_service.load_all(self.feedback_path)
        self.assertEqual(len(records), 3)
        self.assertEqual([r["scene_id"] for r in records], [0, 1, 2])

    def test_record_returns_the_appended_entry(self):
        entry = asset_feedback_service.record(
            scene_id=5,
            provider="pixabay_video",
            asset_type="video",
            selected_asset="images/scene5.png",
            outcome="success",
            feedback_path=self.feedback_path,
        )

        self.assertEqual(entry["scene_id"], 5)
        self.assertEqual(entry["provider"], "pixabay_video")

    def test_corrupted_feedback_file_treated_as_empty(self):
        with open(self.feedback_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        self.assertEqual(asset_feedback_service.load_all(self.feedback_path), [])

    def test_record_recovers_after_corrupted_file(self):
        with open(self.feedback_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        asset_feedback_service.record(
            scene_id=1,
            provider="pexels_image",
            asset_type="image",
            selected_asset="images/scene1.png",
            outcome="success",
            feedback_path=self.feedback_path,
        )

        records = asset_feedback_service.load_all(self.feedback_path)
        self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
