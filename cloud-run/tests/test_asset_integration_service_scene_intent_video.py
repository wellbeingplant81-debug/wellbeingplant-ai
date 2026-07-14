"""
Sprint100-3 - integrate_asset()이 prefer_video를 실제 select_best_
with_score() 호출까지 그대로 전달하는지 확인한다(select_best_with_
score/score_asset은 mock하지 않고 실제로 실행해, asset_strategy가
select_best_with_score 호출에서 그냥 누락되던 기존 배선 버그
(Sprint96.1 hotfix가 실제로는 한 번도 적용되지 않던 문제)가 재발하지
않는지 증명한다).
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.video_relevance import VideoRelevanceScore
from app.services.asset_integration_service import integrate_asset


SAMPLE_SCENE = {
    "scene": 2,
    "narration": "매일 30분씩 걷는 습관을 만들어 보세요.",
    "image_prompt": "a person walking in a park",
}

PEXELS_IMAGE_CANDIDATE = {
    "source": "pexels_image", "download_url": "img.jpg", "source_url": "u",
    "width": 1080, "height": 1920, "query": "walking park",
}

PEXELS_VIDEO_CANDIDATE = {
    "source": "pexels_video", "download_url": "vid.mp4", "source_url": "u2",
    "width": 1920, "height": 1080, "query": "walking park",
}


def _download_candidate_side_effect(content=b"fake bytes"):
    def _side_effect(candidate, output_file):
        with open(output_file, "wb") as f:
            f.write(content)
        return {
            "source": candidate["source"],
            "local_path": output_file,
            "metadata": {"query": candidate.get("query")},
        }
    return _side_effect


class TestIntegrateAssetSceneIntentVideo(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name
        os.makedirs(os.path.join(self.project_path, "images"), exist_ok=True)

        feedback_patcher = patch(
            "app.services.asset_integration_service.asset_feedback_service.record",
        )
        self.addCleanup(feedback_patcher.stop)
        feedback_patcher.start()

        ranking_patcher = patch(
            "app.services.asset_ranking_service.load_all",
            return_value=[],
        )
        self.addCleanup(ranking_patcher.stop)
        ranking_patcher.start()

    @patch("app.services.asset_integration_service.video_relevance_service.score_relevance")
    @patch("app.services.asset_integration_service.subprocess.run")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_prefer_video_true_selects_video_when_relevant(
        self, mock_get_candidates, mock_download, mock_subprocess_run, mock_score,
    ):
        mock_get_candidates.return_value = [
            PEXELS_IMAGE_CANDIDATE, PEXELS_VIDEO_CANDIDATE,
        ]
        mock_download.side_effect = _download_candidate_side_effect()
        mock_score.return_value = VideoRelevanceScore(score=0.9, reasoning="일치")

        def _ffmpeg_side_effect(command, capture_output, text):
            output_path = command[-1]
            with open(output_path, "wb") as f:
                f.write(b"fake frame bytes")
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = "10.0"
            return mock_result

        mock_subprocess_run.side_effect = _ffmpeg_side_effect

        result = integrate_asset(
            SAMPLE_SCENE, self.project_path,
            prefer_ai=False, asset_strategy="upload", prefer_video=True,
        )

        self.assertEqual(result["provider"], "pexels_video")
        self.assertIn("video_relevance_trace", result)

    @patch("app.services.asset_integration_service.video_relevance_service.score_relevance")
    @patch("app.services.asset_integration_service.subprocess.run")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_prefer_video_true_falls_back_to_image_when_video_irrelevant(
        self, mock_get_candidates, mock_download, mock_subprocess_run, mock_score,
    ):
        """
        Sprint100-3.1 (RED->GREEN) - 2026-07-13 Production QA에서 실측한
        버그: video 후보가 있었지만 전부 관련성 기준 미달이었는데도,
        폴백 랭킹이 prefer_video=True를 그대로 써서 SCENE_INTENT_VIDEO_
        BONUS가 다시 적용되어 무관하다고 판정한 video가 또 선택됐다.
        지금은 폴백에서 video 후보 자체를 제외해야 한다.
        """
        mock_get_candidates.return_value = [
            PEXELS_IMAGE_CANDIDATE, PEXELS_VIDEO_CANDIDATE,
        ]
        mock_download.side_effect = _download_candidate_side_effect()
        mock_score.return_value = VideoRelevanceScore(score=0.1, reasoning="무관")

        def _ffmpeg_side_effect(command, capture_output, text):
            output_path = command[-1]
            with open(output_path, "wb") as f:
                f.write(b"fake frame bytes")
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_result.stdout = "10.0"
            return mock_result

        mock_subprocess_run.side_effect = _ffmpeg_side_effect

        result = integrate_asset(
            SAMPLE_SCENE, self.project_path,
            prefer_ai=False, asset_strategy="upload", prefer_video=True,
        )

        self.assertEqual(result["provider"], "pexels_image")

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_prefer_video_false_keeps_image_winning_in_upload_strategy(
        self, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [
            PEXELS_IMAGE_CANDIDATE, PEXELS_VIDEO_CANDIDATE,
        ]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(
            SAMPLE_SCENE, self.project_path,
            prefer_ai=False, asset_strategy="upload", prefer_video=False,
        )

        self.assertEqual(result["provider"], "pexels_image")


if __name__ == "__main__":
    unittest.main()
