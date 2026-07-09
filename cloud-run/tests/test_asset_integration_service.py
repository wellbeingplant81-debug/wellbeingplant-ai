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

        # Sprint62-5: subprompt_service.generate_subprompts()가 실제
        # Gemini API를 호출하지 않도록, 기본적으로 image_prompt를
        # count번 반복하는 폴백 동작으로 고정한다(서브프롬프트 분할
        # 자체를 검증하는 테스트는 test_asset_generation_multi_assets.py
        # 에서 개별적으로 override한다).
        subprompt_patcher = patch(
            "app.services.asset_integration_service.subprompt_service.generate_subprompts",
            side_effect=lambda image_prompt, count=4: [image_prompt] * count,
        )
        self.addCleanup(subprompt_patcher.stop)
        subprompt_patcher.start()

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

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
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

    @patch("app.services.asset_integration_service.select_best_with_score")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_is_hook_scene_true_for_scene_one(
        self, mock_get_candidates, mock_download, mock_select_best_with_score,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_select_best_with_score.return_value = (PEXELS_IMAGE_CANDIDATE, 0.92)
        mock_download.side_effect = _download_candidate_side_effect()

        hook_scene = {**SAMPLE_SCENE, "scene": 1}
        integrate_asset(hook_scene, self.project_path)

        _, kwargs = mock_select_best_with_score.call_args
        self.assertTrue(kwargs["is_hook_scene"])

    @patch("app.services.asset_integration_service.select_best_with_score")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_is_hook_scene_false_for_non_first_scene(
        self, mock_get_candidates, mock_download, mock_select_best_with_score,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_select_best_with_score.return_value = (PEXELS_IMAGE_CANDIDATE, 0.92)
        mock_download.side_effect = _download_candidate_side_effect()

        integrate_asset(SAMPLE_SCENE, self.project_path)

        _, kwargs = mock_select_best_with_score.call_args
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

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
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

    # --- Sprint38: Hybrid Asset Engine (prefer_ai quality gate) ---

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_prefer_ai_false_behaves_exactly_like_before(
        self, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path, prefer_ai=False)

        self.assertEqual(result["provider"], "pexels_image")
        self.mock_record.assert_called_once_with(
            scene_id=2,
            provider="pexels_image",
            asset_type="image",
            selected_asset=result["asset_path"],
            outcome="success",
        )

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_prefer_ai_true_still_uses_pexels_when_quality_is_high_enough(
        self, mock_get_candidates, mock_download, mock_generate_image,
    ):
        # PEXELS_IMAGE_CANDIDATE는 portrait라 0.92점 - balanced 모드의
        # pexels_quality_threshold(0.90)를 넘으므로, AI 우선 scene이어도
        # 비용보다 품질을 우선해 Pexels가 그대로 채택돼야 한다.
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path, prefer_ai=True)

        self.assertEqual(result["provider"], "pexels_image")
        mock_generate_image.assert_not_called()
        self.mock_record.assert_called_once_with(
            scene_id=2,
            provider="pexels_image",
            asset_type="image",
            selected_asset=result["asset_path"],
            outcome="success",
        )

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_prefer_ai_true_uses_ai_when_pexels_quality_is_too_low(
        self, mock_get_candidates, mock_download, mock_generate_image,
    ):
        # landscape(비-portrait) pixabay_image는 0.85점 - balanced 모드의
        # 0.90 문턱을 못 넘으므로 AI로 생성돼야 한다.
        low_quality_candidate = {
            "source": "pixabay_image", "download_url": "img.jpg", "source_url": "u",
            "width": 1920, "height": 1080, "query": "tired woman office",
        }
        mock_get_candidates.return_value = [low_quality_candidate]

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        result = integrate_asset(SAMPLE_SCENE, self.project_path, prefer_ai=True)

        self.assertEqual(result["provider"], "ai_image")
        mock_download.assert_not_called()

        _, kwargs = self.mock_record.call_args
        self.assertEqual(kwargs["outcome"], "ai_priority")
        self.assertEqual(kwargs["provider"], "ai_image")

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_prefer_ai_true_with_no_candidates_is_still_reported_as_fallback(
        self, mock_get_candidates, mock_generate_image,
    ):
        # 진짜 후보가 아예 없었으면(품질 비교 대상 자체가 없음) 의도적
        # 선택("ai_priority")이 아니라 기존과 같은 "fallback"이어야 한다.
        mock_get_candidates.return_value = []

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        integrate_asset(SAMPLE_SCENE, self.project_path, prefer_ai=True)

        _, kwargs = self.mock_record.call_args
        self.assertEqual(kwargs["outcome"], "fallback")

    # --- Sprint60: Smart Visual Selection v1 (visual_type hard branch) ---

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_visual_type_real_uses_pexels_first(
        self, mock_get_candidates, mock_download, mock_generate_image,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        result = integrate_asset(scene, self.project_path)

        self.assertEqual(result["provider"], "pexels_image")
        mock_generate_image.assert_not_called()

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_visual_type_real_falls_back_to_ai_when_no_candidates(
        self, mock_get_candidates, mock_generate_image,
    ):
        mock_get_candidates.return_value = []

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        result = integrate_asset(scene, self.project_path)

        self.assertEqual(result["provider"], "ai_image")
        _, kwargs = self.mock_record.call_args
        self.assertEqual(kwargs["outcome"], "fallback")

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_visual_type_real_falls_back_to_ai_when_download_fails(
        self, mock_get_candidates, mock_download, mock_generate_image,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = Exception("network error")

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        result = integrate_asset(scene, self.project_path)

        self.assertEqual(result["provider"], "ai_image")

    @patch("app.services.asset_integration_service.get_candidates")
    @patch("app.services.asset_integration_service.generate_image")
    def test_visual_type_ai_uses_imagen_first(
        self, mock_generate_image, mock_get_candidates,
    ):
        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        self.assertEqual(result["provider"], "ai_image")
        mock_get_candidates.assert_not_called()
        _, kwargs = self.mock_record.call_args
        self.assertEqual(kwargs["outcome"], "ai_priority")

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    @patch("app.services.asset_integration_service.generate_image")
    def test_visual_type_ai_falls_back_to_pexels_when_imagen_fails(
        self, mock_generate_image, mock_get_candidates, mock_download,
    ):
        mock_generate_image.side_effect = Exception("imagen quota exceeded")
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        self.assertEqual(result["provider"], "pexels_image")
        _, kwargs = self.mock_record.call_args
        self.assertEqual(kwargs["outcome"], "success")

    @patch("app.services.asset_integration_service.get_candidates")
    @patch("app.services.asset_integration_service.generate_image")
    def test_visual_type_ai_raises_when_both_imagen_and_pexels_fail(
        self, mock_generate_image, mock_get_candidates,
    ):
        mock_generate_image.side_effect = Exception("imagen quota exceeded")
        mock_get_candidates.return_value = []

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}

        with self.assertRaises(Exception):
            integrate_asset(scene, self.project_path)

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_visual_type_absent_preserves_prefer_ai_default_behavior(
        self, mock_get_candidates, mock_download,
    ):
        # visual_type이 없는 기존 scene(SAMPLE_SCENE)은 Sprint38의
        # prefer_ai 소프트 게이트 경로를 그대로 타야 한다 - visual_type
        # 필드 자체가 없어도 KeyError 없이 동작함을 명시적으로 확인한다.
        self.assertNotIn("visual_type", SAMPLE_SCENE)
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(result["provider"], "pexels_image")

    # --- Sprint60 Hotfix 문제1: generate_image가 visual_type을 받아야
    # 의료 일러스트 스타일 분기(image_service.py)가 실제로 동작한다 ---

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_visual_type_ai_passes_visual_type_to_generate_image(
        self, mock_get_candidates, mock_generate_image,
    ):
        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        integrate_asset(scene, self.project_path)

        _, kwargs = mock_generate_image.call_args
        self.assertEqual(kwargs["visual_type"], "ai")

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_visual_type_real_fallback_passes_visual_type_to_generate_image(
        self, mock_get_candidates, mock_generate_image,
    ):
        # visual_type="real"인 scene이 Pexels 실패로 AI 폴백을 타도,
        # generate_image에는 "real"이 그대로 전달돼야 한다(의료 스타일이
        # 아니라 기존 photorealistic 스타일을 써야 하므로).
        mock_get_candidates.return_value = []

        def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _generate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "real"}
        integrate_asset(scene, self.project_path)

        _, kwargs = mock_generate_image.call_args
        self.assertEqual(kwargs["visual_type"], "real")

    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_visual_type_absent_passes_none_to_generate_image(
        self, mock_get_candidates, mock_download,
    ):
        mock_get_candidates.return_value = []

        with patch(
            "app.services.asset_integration_service.generate_image",
        ) as mock_generate_image:

            def _generate_side_effect(image_prompt, output_file, channel="wellbeing", is_hook_scene=False, visual_type=None):
                with open(output_file, "wb") as f:
                    f.write(b"ai bytes")
                return output_file

            mock_generate_image.side_effect = _generate_side_effect

            integrate_asset(SAMPLE_SCENE, self.project_path)

            _, kwargs = mock_generate_image.call_args
            self.assertIsNone(kwargs["visual_type"])


if __name__ == "__main__":
    unittest.main()
