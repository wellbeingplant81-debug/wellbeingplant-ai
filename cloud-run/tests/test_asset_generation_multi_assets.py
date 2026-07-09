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

        # Sprint62-5: 기본적으로 subprompt_service.generate_subprompts()가
        # 실제 Gemini API를 호출하지 않도록 image_prompt를 count번
        # 반복하는 폴백 동작으로 고정한다. 서브프롬프트 분할 자체를
        # 검증하는 테스트는 개별적으로 이 mock을 override한다.
        subprompt_patcher = patch(
            "app.services.asset_integration_service.subprompt_service.generate_subprompts",
            side_effect=lambda image_prompt, count=4: [image_prompt] * count,
        )
        self.addCleanup(subprompt_patcher.stop)
        self.mock_generate_subprompts = subprompt_patcher.start()

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

    # --- Sprint62-5: 추가 AI asset은 서브프롬프트를 사용한다 ---

    @patch("app.services.asset_integration_service.subprompt_service.generate_subprompts")
    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_extra_assets_use_distinct_subprompts_when_available(
        self, mock_get_candidates, mock_generate_image, mock_generate_subprompts,
    ):
        subprompts = ["primary framing", "close-up", "wide shot", "side angle"]
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect
        mock_generate_subprompts.return_value = subprompts

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        extra_prompts_used = [
            call.args[0] for call in mock_generate_image.call_args_list[1:]
        ]
        self.assertEqual(extra_prompts_used, subprompts[1:])

        extra_asset_prompts = [asset["prompt"] for asset in result["assets"][1:]]
        self.assertEqual(extra_asset_prompts, subprompts[1:])

    @patch("app.services.asset_integration_service.subprompt_service.generate_subprompts")
    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_primary_asset_still_uses_raw_image_prompt(
        self, mock_get_candidates, mock_generate_image, mock_generate_subprompts,
    ):
        # 1차 asset(asset_path)은 이번 스프린트에서 손대지 않는다 -
        # 서브프롬프트가 있어도 원본 image_prompt로 생성돼야 한다.
        subprompts = ["primary framing", "close-up", "wide shot", "side angle"]
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect
        mock_generate_subprompts.return_value = subprompts

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        first_call_prompt = mock_generate_image.call_args_list[0].args[0]
        self.assertEqual(first_call_prompt, SAMPLE_SCENE["image_prompt"])
        self.assertEqual(result["assets"][0]["prompt"], SAMPLE_SCENE["image_prompt"])

    @patch("app.services.asset_integration_service.subprompt_service.generate_subprompts")
    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_subprompt_service_called_with_image_prompt_and_asset_count(
        self, mock_get_candidates, mock_generate_image, mock_generate_subprompts,
    ):
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect
        mock_generate_subprompts.return_value = [
            "a", "b", "c", "d",
        ]

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        integrate_asset(scene, self.project_path)

        mock_generate_subprompts.assert_called_once_with(
            SAMPLE_SCENE["image_prompt"], count=4,
        )

    @patch("app.services.asset_integration_service.subprompt_service.generate_subprompts")
    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_extra_assets_fall_back_to_image_prompt_when_subprompt_service_falls_back(
        self, mock_get_candidates, mock_generate_image, mock_generate_subprompts,
    ):
        # 서브프롬프트 생성이 실패하면 subprompt_service 자체가
        # image_prompt를 4번 반복한 리스트로 폴백한다(test_subprompt_
        # service.py에서 검증) - 이 폴백 결과를 그대로 받았을 때도
        # 추가 asset 생성이 기존 image_prompt로 정상 동작해야 한다.
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect
        mock_generate_subprompts.return_value = [SAMPLE_SCENE["image_prompt"]] * 4

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        for asset in result["assets"]:
            self.assertEqual(asset["prompt"], SAMPLE_SCENE["image_prompt"])
        for call in mock_generate_image.call_args_list:
            self.assertEqual(call.args[0], SAMPLE_SCENE["image_prompt"])

    @patch("app.services.asset_integration_service.subprompt_service.generate_subprompts")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_stock_sourced_scene_never_calls_subprompt_service(
        self, mock_get_candidates, mock_download, mock_generate_subprompts,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        integrate_asset(SAMPLE_SCENE, self.project_path)

        mock_generate_subprompts.assert_not_called()


class TestAssetRoleMetadata(unittest.TestCase):
    """
    Sprint64-2 - Asset Role Metadata. AI 4-asset 경로(source ==
    "ai_image")에서만 각 asset에 role(environment/subject/detail/
    transition)을 인덱스 순서대로 부여한다. 스톡/비디오프레임 단일
    asset은 role 없이(Sprint62-1~64-1과 완전히 동일하게) 그대로
    둔다 - 하위 호환을 위해 role 유무와 무관하게 asset.get("role")로
    다뤄야 한다.
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

        subprompt_patcher = patch(
            "app.services.asset_integration_service.subprompt_service.generate_subprompts",
            side_effect=lambda image_prompt, count=4: [image_prompt] * count,
        )
        self.addCleanup(subprompt_patcher.stop)
        subprompt_patcher.start()

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_ai_generated_assets_get_roles_in_order(
        self, mock_get_candidates, mock_generate_image,
    ):
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        roles = [asset["role"] for asset in result["assets"]]
        self.assertEqual(roles, ["environment", "subject", "detail", "transition"])

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_ai_fallback_path_also_gets_roles(
        self, mock_get_candidates, mock_generate_image,
    ):
        # visual_type 없이(스톡 후보가 아예 없어 AI로 폴백한 경우)도
        # 최종 source가 ai_image이면 동일하게 role이 붙어야 한다.
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        roles = [asset["role"] for asset in result["assets"]]
        self.assertEqual(roles, ["environment", "subject", "detail", "transition"])

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_stock_sourced_scene_has_no_role_field(
        self, mock_get_candidates, mock_download, mock_generate_image,
    ):
        mock_get_candidates.return_value = [PEXELS_IMAGE_CANDIDATE]
        mock_download.side_effect = _download_candidate_side_effect()

        result = integrate_asset(SAMPLE_SCENE, self.project_path)

        self.assertEqual(len(result["assets"]), 1)
        self.assertNotIn("role", result["assets"][0])
        mock_generate_image.assert_not_called()

    @patch("app.services.asset_integration_service.subprocess.run")
    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.download_candidate")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_video_frame_extraction_scene_has_no_role_field(
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
        self.assertNotIn("role", result["assets"][0])
        mock_generate_image.assert_not_called()

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_role_survives_regardless_of_get_accessor_usage(
        self, mock_get_candidates, mock_generate_image,
    ):
        # 하위 호환 확인: role이 있는 asset도 .get("role")로 안전하게
        # 접근 가능해야 한다(KeyError 없음).
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_image_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        result = integrate_asset(scene, self.project_path)

        for asset in result["assets"]:
            self.assertIsNotNone(asset.get("role"))
            self.assertIsNone(asset.get("nonexistent_field"))


if __name__ == "__main__":
    unittest.main()
