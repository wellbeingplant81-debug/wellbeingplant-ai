"""
Sprint96.1 (RED) - Hotfix: UploadAssetStrategy(prefer_ai)와 visual_type
충돌 해결.

integrate_asset()에 optional 파라미터 asset_strategy=None을 추가한다.
asset_strategy가 None/"default"면 지금까지처럼 scene["visual_type"]이
있을 때 prefer_ai를 완전히 무시하고 visual_type을 우선한다(회귀 없음).
asset_strategy=="upload"일 때만 visual_type 유무와 무관하게 prefer_ai로
real/ai를 결정한다(UploadAssetStrategy가 최종 결정권을 가짐). 아직
구현이 없으므로(RED) upload 관련 테스트는 실패해야 정상이다.
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


SAMPLE_SCENE = {
    "scene": 1,
    "narration": "혈관 건강 이야기",
    "image_prompt": "diagram of blood vessel",
}

PEXELS_IMAGE_CANDIDATE = {
    "source": "pexels_image", "download_url": "img.jpg", "source_url": "u",
    "width": 1080, "height": 1920, "query": "q",
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


def _generate_image_side_effect(
    image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None,
):
    with open(output_file, "wb") as f:
        f.write(b"ai bytes")
    return output_file


class TestAssetIntegrationServiceUploadVisualTypeConflict(unittest.TestCase):

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

        subprompt_patcher = patch(
            "app.services.asset_integration_service.subprompt_service.generate_subprompts",
            side_effect=lambda image_prompt, count=4: [image_prompt] * count,
        )
        self.addCleanup(subprompt_patcher.stop)
        subprompt_patcher.start()

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    @patch("app.services.asset_integration_service.generate_image")
    def test_default_visual_type_real_still_wins_even_if_prefer_ai_true(
        self, mock_generate_image, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        result = integrate_asset(scene, self.project_path, prefer_ai=True)

        self.assertEqual(result["provider"], "pexels_image")
        mock_generate_image.assert_not_called()

    @patch("app.services.asset_integration_service.get_candidates")
    @patch("app.services.asset_integration_service.generate_image")
    def test_upload_strategy_prefer_ai_true_overrides_visual_type_real(
        self, mock_generate_image, mock_get_candidates,
    ):
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        result = integrate_asset(
            scene, self.project_path, prefer_ai=True, asset_strategy="upload",
        )

        self.assertEqual(result["provider"], "ai_image")

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    @patch("app.services.asset_integration_service.generate_image")
    def test_upload_strategy_prefer_ai_false_overrides_visual_type_ai(
        self, mock_generate_image, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(
            scene, self.project_path, prefer_ai=False, asset_strategy="upload",
        )

        self.assertEqual(result["provider"], "pexels_image")
        mock_generate_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
