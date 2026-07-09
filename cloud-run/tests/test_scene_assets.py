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
from app.services.video_builder import _resolve_asset_path


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


class TestSceneAssetsStructure(unittest.TestCase):
    """
    Sprint62-1 - Visual Diversity 기반 구조. Scene당 여러 Asset을 지원
    하기 위한 준비 단계로, 기존 scene["asset_path"](Sprint30부터 존재
    하는 실질적인 "image_path" 필드)는 그대로 두고 scene["assets"]에
    동일한 이미지를 담은 항목 하나만 추가한다. 실제 동작(선택되는
    이미지, video_builder가 읽는 경로)은 이번 스프린트에서 전혀
    바뀌지 않는다.
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

    # --- 기존 Scene 데이터 로드 가능 ---

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_scene_without_assets_key_loads_without_error(
        self, mock_get_candidates, mock_download,
    ):
        self.assertNotIn("assets", SAMPLE_SCENE)
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertIn("assets", result)

    # --- assets 생성 확인 ---

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_assets_contains_single_image_entry_matching_asset_path(
        self, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(
            result["assets"],
            [{
                "type": "image",
                "path": result["asset_path"],
                "prompt": SAMPLE_SCENE["image_prompt"],
            }],
        )

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_assets_populated_for_ai_fallback_path(
        self, mock_get_candidates, mock_generate_image,
    ):
        mock_get_candidates.return_value = []

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(len(result["assets"]), 1)
        self.assertEqual(result["assets"][0]["path"], result["asset_path"])

    @patch("app.services.asset_integration_service.subprocess.run")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_assets_type_is_image_even_for_extracted_video_frame(
        self, mock_get_candidates, mock_download, mock_subprocess_run,
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
        self.assertEqual(result["assets"][0]["type"], "image")
        self.assertEqual(result["assets"][0]["path"], result["asset_path"])

    # --- image_path(=asset_path) 유지 확인 ---

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_asset_path_field_unchanged_by_assets_addition(
        self, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        expected_path = os.path.join(self.project_path, "images", "scene2.png")
        self.assertEqual(result["asset_path"], expected_path)

    # --- 기존 코드와 하위 호환 확인 ---

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_video_builder_still_resolves_asset_path_when_assets_present(
        self, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertIn("assets", result)
        resolved = _resolve_asset_path(self.project_path, result)
        self.assertEqual(resolved, result["asset_path"])

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_scene_without_assets_key_still_resolves_via_video_builder(
        self, mock_get_candidates, mock_download,
    ):
        # video_builder는 assets 필드 유무와 무관하게 asset_path만
        # 보고 동작해야 한다 (하위 호환 - Sprint62-1 이전 데이터도 그대로).
        legacy_scene = dict(SAMPLE_SCENE)
        legacy_scene["asset_path"] = os.path.join(
            self.project_path, "images", "scene2.png",
        )

        resolved = _resolve_asset_path(self.project_path, legacy_scene)

        self.assertEqual(resolved, legacy_scene["asset_path"])

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_original_scene_dict_not_mutated_by_assets_addition(
        self, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        scene_copy = dict(SAMPLE_SCENE)
        integrate_asset(scene_copy, self.project_path)

        self.assertNotIn("assets", scene_copy)
        self.assertEqual(scene_copy, SAMPLE_SCENE)


if __name__ == "__main__":
    unittest.main()
