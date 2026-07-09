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
    "scene": 2,
    "narration": "밤마다 화장실 때문에 자주 깨시나요?",
    "image_prompt": "Ultra realistic photo of a tired woman in a messy office.",
}

PEXELS_IMAGE_CANDIDATE = {
    "source": "pexels_image", "download_url": "img.jpg", "source_url": "u",
    "width": 1080, "height": 1920, "query": "tired woman office",
}

PEXELS_VIDEO_CANDIDATE = {
    "source": "pexels_video", "download_url": "vid.mp4", "source_url": "u3",
    "width": 1080, "height": 1920, "query": "tired woman office",
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


def _generate_image_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
    with open(output_file, "wb") as f:
        f.write(b"ai bytes")
    return output_file


class TestMultiAssetGeneration(unittest.TestCase):
    """
    Sprint62-4 - Visual Diversity 첫 단계: 1차 asset이 AI(Imagen)로
    생성된 scene에 한해, 동일한 image_prompt로 추가 이미지 3개를 더
    생성해 scene당 asset 4개를 만든다. 스톡(Pexels/Pixabay)이 선택된
    scene은 이번 스프린트에서 손대지 않는다(assets 1개 그대로) -
    프롬프트 다양화 및 스톡 다중 후보 작업은 다음 스프린트 범위.
    """

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

    # --- Scene당 4개 asset 생성 (AI 경로) ---

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_ai_generated_scene_produces_four_assets(
        self, mock_get_candidates, mock_generate_image,
    ):
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        self.assertEqual(len(result["assets"]), 4)
        self.assertEqual(mock_generate_image.call_count, 4)

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_ai_fallback_scene_also_produces_four_assets(
        self, mock_get_candidates, mock_generate_image,
    ):
        # visual_type 없이도(스톡 후보가 아예 없어 AI로 폴백한 경우)
        # 최종 source가 ai_image이면 동일하게 4개를 생성해야 한다.
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["provider"], "ai_image")
        self.assertEqual(len(result["assets"]), 4)

    # --- asset_path == assets[0].path 유지 ---

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_asset_path_equals_first_asset_path(
        self, mock_get_candidates, mock_generate_image,
    ):
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        self.assertEqual(result["asset_path"], result["assets"][0]["path"])

    # --- assets 순서 보존 및 동일 prompt 재사용 ---

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_assets_all_share_same_prompt_and_have_distinct_paths(
        self, mock_get_candidates, mock_generate_image,
    ):
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        prompts_used = [asset["prompt"] for asset in result["assets"]]
        self.assertEqual(prompts_used, [SAMPLE_SCENE["image_prompt"]] * 4)

        paths_used = [asset["path"] for asset in result["assets"]]
        self.assertEqual(len(paths_used), len(set(paths_used)))

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_all_generate_image_calls_use_same_prompt(
        self, mock_get_candidates, mock_generate_image,
    ):
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        integrate_asset(scene, self.project_path)

        for call in mock_generate_image.call_args_list:
            self.assertEqual(call.args[0], SAMPLE_SCENE["image_prompt"])

    # --- 스톡 선택 scene은 회귀 없음(assets 1개 그대로) ---

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_stock_sourced_scene_keeps_single_asset(
        self, mock_get_candidates, mock_download, mock_generate_image,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["provider"], "pexels_image")
        self.assertEqual(len(result["assets"]), 1)
        mock_generate_image.assert_not_called()

    @patch("app.services.asset_integration_service.subprocess.run")
    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_video_frame_extraction_scene_keeps_single_asset(
        self, mock_get_candidates, mock_download, mock_generate_image, mock_subprocess_run,
    ):
        mock_get_candidates.return_value = [PEXELS_VIDEO_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect(
            content=b"fake video bytes",
        )

        def _ffmpeg_side_effect(command, capture_output, text):
            output_path = command[-1]
            with open(output_path, "wb") as f:
                f.write(b"fake frame bytes")
            from unittest.mock import MagicMock
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            return mock_result

        mock_subprocess_run.side_effect = _ffmpeg_side_effect

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["asset_type"], "video")
        self.assertEqual(len(result["assets"]), 1)
        mock_generate_image.assert_not_called()

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_prefer_ai_false_default_behavior_unaffected(
        self, mock_get_candidates, mock_download, mock_generate_image,
    ):
        # 기존 Sprint38 prefer_ai=False 기본 경로(visual_type 없음)도
        # 스톡이 선택되면 그대로 assets 1개 유지되어야 한다.
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path, prefer_ai=False)

        self.assertEqual(len(result["assets"]), 1)
        mock_generate_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
