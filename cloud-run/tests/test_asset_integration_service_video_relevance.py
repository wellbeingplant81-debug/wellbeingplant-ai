"""
Sprint100-3.1 - _select_relevant_video_candidate()가 여러 video 후보를
순회하며 대표 프레임을 뽑아 채점하고, RELEVANCE_THRESHOLD 이상인
후보 중 최고점을 선택하는지, 통과하는 후보가 없으면 (None, trace)로
폴백 신호를 주는지 확인한다. download_candidate/_extract_frame_at_
fraction/video_relevance_service.score_relevance는 모두 mock한다 -
실제 네트워크/ffmpeg/Gemini 호출 없이 오케스트레이션 로직만 검증한다.
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
from app.services import asset_integration_service as svc


VIDEO_A = {"source": "pexels_video", "download_url": "a.mp4", "query": "walking a"}
VIDEO_B = {"source": "pexels_video", "download_url": "b.mp4", "query": "walking b"}
VIDEO_C = {"source": "pexels_video", "download_url": "c.mp4", "query": "walking c"}


def _download_side_effect(candidate, output_file):
    with open(output_file, "wb") as f:
        f.write(b"fake video bytes")
    return {"source": candidate["source"], "local_path": output_file, "metadata": {"query": candidate["query"]}}


class TestSelectRelevantVideoCandidate(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.staging_prefix = os.path.join(self._tmp_dir.name, "scene1")

    @patch("app.services.asset_integration_service.video_relevance_service.score_relevance")
    @patch("app.services.asset_integration_service._extract_frame_at_fraction")
    @patch("app.services.asset_integration_service.download_candidate")
    def test_selects_highest_scoring_candidate_above_threshold(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.side_effect = [
            VideoRelevanceScore(score=0.3, reasoning="관련 없음"),
            VideoRelevanceScore(score=0.9, reasoning="매우 관련 있음"),
        ]

        result, trace = svc._select_relevant_video_candidate(
            [VIDEO_A, VIDEO_B], narration="산책", image_prompt="walking",
            staging_path_prefix=self.staging_prefix,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "pexels_video")
        self.assertTrue(result["already_frame"])
        self.assertEqual(len(trace), 2)
        self.assertEqual(trace[0]["score"], 0.3)
        self.assertEqual(trace[1]["score"], 0.9)

    @patch("app.services.asset_integration_service.video_relevance_service.score_relevance")
    @patch("app.services.asset_integration_service._extract_frame_at_fraction")
    @patch("app.services.asset_integration_service.download_candidate")
    def test_no_candidate_above_threshold_returns_none(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.side_effect = [
            VideoRelevanceScore(score=0.2, reasoning="관련 없음"),
            VideoRelevanceScore(score=0.4, reasoning="약간 관련"),
        ]

        result, trace = svc._select_relevant_video_candidate(
            [VIDEO_A, VIDEO_B], narration="산책", image_prompt="walking",
            staging_path_prefix=self.staging_prefix,
        )

        self.assertIsNone(result)
        self.assertEqual(len(trace), 2)

    @patch("app.services.asset_integration_service.video_relevance_service.score_relevance")
    @patch("app.services.asset_integration_service._extract_frame_at_fraction")
    @patch("app.services.asset_integration_service.download_candidate")
    def test_caps_candidates_at_max_relevance_candidates(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.return_value = VideoRelevanceScore(score=0.9, reasoning="ok")

        svc._select_relevant_video_candidate(
            [VIDEO_A, VIDEO_B, VIDEO_C], narration="산책", image_prompt="walking",
            staging_path_prefix=self.staging_prefix,
        )

        self.assertLessEqual(mock_score.call_count, svc.MAX_RELEVANCE_CANDIDATES)

    @patch("app.services.asset_integration_service.video_relevance_service.score_relevance")
    @patch("app.services.asset_integration_service._extract_frame_at_fraction")
    @patch("app.services.asset_integration_service.download_candidate")
    def test_candidate_scoring_error_is_recorded_and_skipped(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.side_effect = [
            Exception("gemini timeout"),
            VideoRelevanceScore(score=0.9, reasoning="ok"),
        ]

        result, trace = svc._select_relevant_video_candidate(
            [VIDEO_A, VIDEO_B], narration="산책", image_prompt="walking",
            staging_path_prefix=self.staging_prefix,
        )

        self.assertIsNotNone(result)
        self.assertIn("error", trace[0])
        self.assertEqual(trace[1]["score"], 0.9)


if __name__ == "__main__":
    unittest.main()
