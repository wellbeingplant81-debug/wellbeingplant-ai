"""
Sprint100-4 - Visual Intelligence Completion. asset_selector.
select_with_relevance()가 AI Image/Stock Image/Stock Video를 동일한
기준으로 채점하고, 후보를 전부 평가한 뒤(중간에 통과해도 멈추지
않음) 최고점을 고르는지, 통과하는 후보가 없을 때 all_failed=True를
반환하면서도 최선의 결과를 계속 반환하는지 확인한다.
download_candidate/_extract_frame_at_fraction/video_relevance_service.
score_relevance는 모두 mock한다 - 실제 네트워크/ffmpeg/Gemini 호출
없이 오케스트레이션 로직만 검증한다.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.models.video_relevance import VideoRelevanceScore
from app.services import asset_selector


VIDEO_A = {"source": "pexels_video", "download_url": "a.mp4", "query": "video a"}
VIDEO_B = {"source": "pexels_video", "download_url": "b.mp4", "query": "video b"}
IMAGE_A = {"source": "pexels_image", "download_url": "a.jpg", "query": "image a"}


def _download_side_effect(candidate, output_file):
    with open(output_file, "wb") as f:
        f.write(b"fake bytes")
    return {"source": candidate["source"], "local_path": output_file, "metadata": {"query": candidate["query"]}}


class TestSelectWithRelevance(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp_dir.cleanup)
        self.staging_prefix = os.path.join(self._tmp_dir.name, "scene1")

    def test_empty_candidates_returns_none_and_all_failed(self):
        result, trace, all_failed = asset_selector.select_with_relevance(
            [], "narration", "prompt", self.staging_prefix,
        )
        self.assertIsNone(result)
        self.assertEqual(trace, [])
        self.assertTrue(all_failed)

    @patch("app.services.asset_selector.video_relevance_service.score_relevance")
    @patch("app.services.asset_selector._extract_frame_at_fraction")
    @patch("app.services.asset_selector.download_candidate")
    def test_evaluates_all_candidates_and_picks_highest_even_if_not_first(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        # Video1=82(통과), Video2=61(통과), Image=91(통과) - 전부 통과해도
        # 끝까지 평가한 뒤 최고점(Image, 91)을 선택해야 한다.
        mock_score.side_effect = [
            VideoRelevanceScore(score=0.82, reasoning="video1 관련"),
            VideoRelevanceScore(score=0.61, reasoning="video2 약간 관련"),
            VideoRelevanceScore(score=0.91, reasoning="image 매우 관련"),
        ]

        result, trace, all_failed = asset_selector.select_with_relevance(
            [VIDEO_A, VIDEO_B, IMAGE_A], "narration", "prompt", self.staging_prefix,
        )

        self.assertFalse(all_failed)
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "pexels_image")
        self.assertEqual(len(trace), 3)
        selected = [c for c in trace if c.get("selected")]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["type"], "image")
        self.assertEqual(selected[0]["score"], 0.91)

    @patch("app.services.asset_selector.video_relevance_service.score_relevance")
    @patch("app.services.asset_selector._extract_frame_at_fraction")
    @patch("app.services.asset_selector.download_candidate")
    def test_all_below_threshold_still_returns_best_but_flags_all_failed(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.side_effect = [
            VideoRelevanceScore(score=0.10, reasoning="무관"),
            VideoRelevanceScore(score=0.30, reasoning="약간 무관"),
        ]

        result, trace, all_failed = asset_selector.select_with_relevance(
            [VIDEO_A, IMAGE_A], "narration", "prompt", self.staging_prefix,
        )

        self.assertTrue(all_failed)
        self.assertIsNotNone(result)  # 그래도 최고점 후보는 반환
        self.assertEqual(len(trace), 2)
        self.assertTrue(all(not c["passed"] for c in trace))

    @patch("app.services.asset_selector.video_relevance_service.score_relevance")
    @patch("app.services.asset_selector._extract_frame_at_fraction")
    @patch("app.services.asset_selector.download_candidate")
    def test_first_candidate_fail_still_evaluates_next_candidate(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.side_effect = [
            VideoRelevanceScore(score=0.20, reasoning="1번째 무관 - FAIL"),
            VideoRelevanceScore(score=0.85, reasoning="2번째 관련 - PASS"),
        ]

        result, trace, all_failed = asset_selector.select_with_relevance(
            [VIDEO_A, IMAGE_A], "narration", "prompt", self.staging_prefix,
        )

        self.assertEqual(mock_score.call_count, 2)  # 1번째 FAIL이어도 2번째까지 평가함
        self.assertFalse(all_failed)
        self.assertEqual(result["source"], "pexels_image")
        self.assertFalse(trace[0]["passed"])
        self.assertTrue(trace[1]["passed"])

    @patch("app.services.asset_selector.video_relevance_service.score_relevance")
    @patch("app.services.asset_selector._extract_frame_at_fraction")
    @patch("app.services.asset_selector.download_candidate")
    def test_ai_stock_image_stock_video_use_identical_rule(
        self, mock_download, mock_extract, mock_score,
    ):
        """AI Image/Stock Image/Stock Video 세 종류를 한 번에 섞어
        넘겨도 동일한 score_relevance()/RELEVANCE_THRESHOLD 기준
        하나로만 평가됨을 확인한다(타입별 분기 없음)."""

        ai_path = os.path.join(self._tmp_dir.name, "ai.png")
        with open(ai_path, "wb") as f:
            f.write(b"fake ai image")

        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.side_effect = [
            VideoRelevanceScore(score=0.50, reasoning="video - FAIL"),
            VideoRelevanceScore(score=0.70, reasoning="stock image - PASS"),
            VideoRelevanceScore(score=0.95, reasoning="ai image - PASS, 최고점"),
        ]

        ai_candidate = {"source": "ai_image", "local_path": ai_path, "query": "ai prompt"}

        result, trace, all_failed = asset_selector.select_with_relevance(
            [VIDEO_A, IMAGE_A, ai_candidate], "narration", "prompt", self.staging_prefix,
        )

        self.assertFalse(all_failed)
        self.assertEqual({c["type"] for c in trace}, {"video", "image", "ai_image"})
        self.assertEqual(result["source"], "ai_image")
        self.assertEqual(mock_score.call_count, 3)

    @patch("app.services.asset_selector.video_relevance_service.score_relevance")
    @patch("app.services.asset_selector._extract_frame_at_fraction")
    @patch("app.services.asset_selector.download_candidate")
    def test_video_winner_preserves_raw_mp4_as_video_path(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.return_value = VideoRelevanceScore(score=0.9, reasoning="ok")

        result, trace, all_failed = asset_selector.select_with_relevance(
            [VIDEO_A], "narration", "prompt", self.staging_prefix,
        )

        self.assertFalse(all_failed)
        self.assertIn("video_path", result)
        self.assertTrue(os.path.exists(result["video_path"]))

    @patch("app.services.asset_selector.video_relevance_service.score_relevance")
    def test_pre_generated_local_path_candidate_is_not_downloaded(self, mock_score):
        ai_path = os.path.join(self._tmp_dir.name, "ai.png")
        with open(ai_path, "wb") as f:
            f.write(b"fake ai image")

        mock_score.return_value = VideoRelevanceScore(score=0.95, reasoning="ok")

        ai_candidate = {"source": "ai_image", "local_path": ai_path, "query": "ai prompt"}

        result, trace, all_failed = asset_selector.select_with_relevance(
            [ai_candidate], "narration", "prompt", self.staging_prefix,
        )

        self.assertFalse(all_failed)
        self.assertEqual(result["source"], "ai_image")
        self.assertEqual(result["local_path"], ai_path)
        self.assertEqual(trace[0]["type"], "ai_image")
        # AI 후보는 select_with_relevance()가 다운로드한 적이 없으므로
        # 패자가 되어도(여기서는 유일한 후보라 승자지만) 원본 파일을
        # 지우지 않는다 - 파일이 여전히 존재해야 한다.
        self.assertTrue(os.path.exists(ai_path))

    @patch("app.services.asset_selector.video_relevance_service.score_relevance")
    @patch("app.services.asset_selector._extract_frame_at_fraction")
    @patch("app.services.asset_selector.download_candidate")
    def test_candidate_scoring_error_is_recorded_and_skipped(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.side_effect = [
            Exception("gemini timeout"),
            VideoRelevanceScore(score=0.9, reasoning="ok"),
        ]

        result, trace, all_failed = asset_selector.select_with_relevance(
            [VIDEO_A, IMAGE_A], "narration", "prompt", self.staging_prefix,
        )

        self.assertFalse(all_failed)
        self.assertIn("error", trace[0])
        self.assertEqual(trace[1]["score"], 0.9)

    @patch("app.services.asset_selector.video_relevance_service.score_relevance")
    @patch("app.services.asset_selector._extract_frame_at_fraction")
    @patch("app.services.asset_selector.download_candidate")
    def test_caps_candidates_at_max_relevance_candidates(
        self, mock_download, mock_extract, mock_score,
    ):
        mock_download.side_effect = _download_side_effect
        mock_extract.side_effect = lambda video_path, out, fraction=0.3: out
        mock_score.return_value = VideoRelevanceScore(score=0.9, reasoning="ok")

        extra = {"source": "pexels_image", "download_url": "c.jpg", "query": "image c"}

        asset_selector.select_with_relevance(
            [VIDEO_A, VIDEO_B, IMAGE_A, extra], "narration", "prompt", self.staging_prefix,
        )

        self.assertLessEqual(mock_score.call_count, asset_selector.MAX_RELEVANCE_CANDIDATES)


if __name__ == "__main__":
    unittest.main()
