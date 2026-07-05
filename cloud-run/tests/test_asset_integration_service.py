import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

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

PIXABAY_IMAGE_CANDIDATE = {
    "source": "pixabay_image", "download_url": "img2.jpg", "source_url": "u2",
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


class TestAssetIntegrationService(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.project_path = self._tmp_dir.name
        os.makedirs(os.path.join(self.project_path, "images"), exist_ok=True)

        # Sprint31: integrate_asset()이 이제 asset_feedback_service.record()를
        # 호출한다. 실제 공유 .cache/feedback.json에 테스트 데이터가
        # 쌓이지 않도록 모든 테스트에서 기록 자체를 막는다.
        feedback_patcher = patch(
            "app.services.asset_integration_service.asset_feedback_service.record",
        )
        self.addCleanup(feedback_patcher.stop)
        self.mock_record = feedback_patcher.start()

        # integrate_asset()은 실제 select_best()를 호출하므로(랭킹
        # 로직 자체를 검증하기 위해 대부분 mock하지 않음), 실제 공유
        # feedback.json 상태와 무관하게 Sprint30 시절 점수 비교가
        # 그대로 성립하도록 학습 이력을 없는 것으로 고정한다.
        ranking_patcher = patch(
            "app.services.asset_ranking_service.load_all",
            return_value=[],
        )
        self.addCleanup(ranking_patcher.stop)
        ranking_patcher.start()

    # --- ranking behavior (uses the real select_best/scorer) ---

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_higher_scoring_candidate_wins_between_two_images(
        self, mock_get_candidates, mock_download,
    ):
        # 둘 다 portrait: pexels_image(0.85+0.05+0.02=0.92) >
        # pixabay_image(0.85+0.05+0.0=0.90)
        mock_get_candidates.return_value = [PIXABAY_IMAGE_CANDIDATE, PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["provider"], "pexels_image")
        downloaded_candidate = mock_download.call_args[0][0]
        self.assertEqual(downloaded_candidate["source"], "pexels_image")

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_image_base_score_outranks_video_when_otherwise_equal(
        self, mock_get_candidates, mock_download,
    ):
        # video_frame base(0.80) < stock_image base(0.85)이므로,
        # portrait/미hook 조건이 같으면 이미지가 비디오를 이긴다.
        mock_get_candidates.return_value = [PEXELS_VIDEO_CANDIDATE, PIXABAY_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["provider"], "pixabay_image")
        self.assertEqual(result["asset_type"], "image")

    # --- video frame extraction still works through the new path ---

    @patch("app.services.asset_integration_service.subprocess.run")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_video_only_candidate_gets_frame_extracted(
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
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            return mock_result

        mock_subprocess_run.side_effect = _ffmpeg_side_effect

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        final_path = os.path.join(self.project_path, "images", "scene2.png")
        staging_path = os.path.join(self.project_path, "images", "scene2.raw")

        self.assertEqual(result["asset_type"], "video")
        self.assertEqual(result["provider"], "pexels_video")
        self.assertTrue(os.path.exists(final_path))
        self.assertFalse(os.path.exists(staging_path))

    # --- AI fallback when no candidates exist ---

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_no_candidates_falls_back_to_ai_image(
        self, mock_get_candidates, mock_download, mock_generate_image,
    ):
        mock_get_candidates.return_value = []

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["provider"], "ai_image")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["asset_type"], "image")
        mock_download.assert_not_called()

    # --- is_hook_scene wiring into ranking ---

    @patch("app.services.asset_integration_service.select_best")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_is_hook_scene_true_for_scene_one(
        self, mock_get_candidates, mock_download, mock_select_best,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_select_best.return_value = PEXELS_IMAGE_CANDIDATE
        mock_download.side_effect = _download_candidate_side_effect()

        hook_scene = {**SAMPLE_SCENE, "scene": 1}
        integrate_asset(hook_scene, self.project_path)

        _, kwargs = mock_select_best.call_args
        self.assertTrue(kwargs["is_hook_scene"])

    @patch("app.services.asset_integration_service.select_best")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_is_hook_scene_false_for_non_first_scene(
        self, mock_get_candidates, mock_download, mock_select_best,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_select_best.return_value = PEXELS_IMAGE_CANDIDATE
        mock_download.side_effect = _download_candidate_side_effect()

        integrate_asset(SAMPLE_SCENE, self.project_path)

        _, kwargs = mock_select_best.call_args
        self.assertFalse(kwargs["is_hook_scene"])

    # --- basic invariants ---

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_original_scene_dict_not_mutated(self, mock_get_candidates, mock_download):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        scene_copy = dict(SAMPLE_SCENE)
        integrate_asset(scene_copy, self.project_path)

        self.assertEqual(scene_copy, SAMPLE_SCENE)

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_original_fields_preserved_in_output(self, mock_get_candidates, mock_download):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["scene"], 2)
        self.assertEqual(result["narration"], SAMPLE_SCENE["narration"])
        self.assertEqual(result["image_prompt"], SAMPLE_SCENE["image_prompt"])

    # --- Sprint31: feedback recording wiring ---

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_records_feedback_on_stock_success(self, mock_get_candidates, mock_download):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.mock_record.assert_called_once_with(
            scene_id=2,
            provider="pexels_image",
            asset_type="image",
            selected_asset=result["asset_path"],
            outcome="success",
        )

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_records_feedback_as_fallback_when_ai_used(
        self, mock_get_candidates, mock_generate_image,
    ):
        mock_get_candidates.return_value = []

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        integrate_asset(SAMPLE_SCENE, self.project_path)

        _, kwargs = self.mock_record.call_args
        self.assertEqual(kwargs["outcome"], "fallback")
        self.assertEqual(kwargs["provider"], "ai_image")

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_feedback_recording_failure_does_not_break_selection(
        self, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()
        self.mock_record.side_effect = Exception("disk full")

        # 예외가 전파되지 않고 정상적으로 scene이 반환되어야 한다.
        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["provider"], "pexels_image")


if __name__ == "__main__":
    unittest.main()
