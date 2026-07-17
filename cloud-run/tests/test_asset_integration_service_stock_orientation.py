"""
Sprint122 (GREEN, Stock 크롭 Hotfix) - integrate_asset()이 render_
profile을 받으면 Stock Image 검색(get_candidates)에 image_orientation
("landscape" for Longform, "portrait" for Shorts)을 전달한다.
render_profile을 안 넘기면(기본값 None) get_candidates 호출에 image_
orientation kwarg 자체가 없다 - 기존 호출부/mock과 완전히 하위 호환.

Stock Video 검색 로직/검색 키워드 로직은 이 스프린트에서 전혀 건드리지
않는다 - get_candidates()의 allow_video 인자와 search_query_override는
그대로다.
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

from app.services.asset_integration_service import integrate_asset
from app.services.render_profile import RenderProfile


SAMPLE_SCENE = {
    "scene": 2,
    "narration": "밤마다 화장실 때문에 자주 깨시나요?",
    "image_prompt": "Ultra realistic photo of a tired woman in a messy office.",
}

LONGFORM = RenderProfile.get("longform")
SHORTS = RenderProfile.get("shorts")


def _download_candidate_side_effect(candidate, output_file):
    with open(output_file, "wb") as f:
        f.write(b"fake bytes")
    return {
        "source": candidate["source"],
        "local_path": output_file,
        "metadata": {"query": candidate.get("query")},
    }


class TestIntegrateAssetStockOrientation(unittest.TestCase):

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

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.select_best_with_score")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_longform_render_profile_passes_landscape_orientation(
        self, mock_get_candidates, mock_select_best, mock_download,
    ):
        mock_get_candidates.return_value = [{"source": "pexels_image", "query": "q"}]
        mock_select_best.return_value = ({"source": "pexels_image", "query": "q"}, 0.9)
        mock_download.side_effect = _download_candidate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        integrate_asset(scene, self.project_path, render_profile=LONGFORM)

        _, kwargs = mock_get_candidates.call_args
        self.assertEqual(kwargs["image_orientation"], "landscape")

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.select_best_with_score")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_shorts_render_profile_passes_portrait_orientation(
        self, mock_get_candidates, mock_select_best, mock_download,
    ):
        mock_get_candidates.return_value = [{"source": "pexels_image", "query": "q"}]
        mock_select_best.return_value = ({"source": "pexels_image", "query": "q"}, 0.9)
        mock_download.side_effect = _download_candidate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        integrate_asset(scene, self.project_path, render_profile=SHORTS)

        _, kwargs = mock_get_candidates.call_args
        self.assertEqual(kwargs["image_orientation"], "portrait")

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.select_best_with_score")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_no_render_profile_omits_image_orientation_kwarg(
        self, mock_get_candidates, mock_select_best, mock_download,
    ):
        mock_get_candidates.return_value = [{"source": "pexels_image", "query": "q"}]
        mock_select_best.return_value = ({"source": "pexels_image", "query": "q"}, 0.9)
        mock_download.side_effect = _download_candidate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        integrate_asset(scene, self.project_path)

        _, kwargs = mock_get_candidates.call_args
        self.assertNotIn("image_orientation", kwargs)


if __name__ == "__main__":
    unittest.main()
