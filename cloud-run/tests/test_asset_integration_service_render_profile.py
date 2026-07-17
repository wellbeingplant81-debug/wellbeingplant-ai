"""
Sprint122 (RED) - integrate_asset()이 render_profile(dict, 기본값
None)을 받으면 render_profile["image_aspect_ratio"]를 generate_image()
호출에 aspect_ratio kwarg로 전달한다.

render_profile을 아예 안 넘기는 기존 호출부(test_asset_integration_
service.py 등 수십 개 기존 테스트 포함)는 aspect_ratio kwarg 자체가
추가되지 않아야 한다 - Sprint96.1 Hotfix의 asset_strategy와 동일한
"명시적으로 줬을 때만 kwarg를 보탠다" 관례를 그대로 따른다. 이래야
render_profile을 모르는 기존 generate_image mock(side_effect가
aspect_ratio 파라미터를 선언하지 않음)이 전부 그대로 통과한다.
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


def _generate_side_effect(
    image_prompt, output_file, channel="wellbeing", is_hook_scene=False,
    visual_type=None, aspect_ratio=None,
):
    with open(output_file, "wb") as f:
        f.write(b"ai bytes")
    return output_file


class TestIntegrateAssetRenderProfile(unittest.TestCase):

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

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_longform_render_profile_passes_16_9_aspect_ratio(
        self, mock_get_candidates, mock_generate_image,
    ):
        # extra 슬롯(detail/transition)이 스톡을 시도할 수 있으므로
        # 후보 없음으로 고정해 AI 경로만 확인한다.
        mock_get_candidates.return_value = []
        mock_generate_image.side_effect = _generate_side_effect

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        integrate_asset(scene, self.project_path, render_profile=LONGFORM)

        _, kwargs = mock_generate_image.call_args
        self.assertEqual(kwargs["aspect_ratio"], "16:9")

    @patch("app.services.asset_integration_service.generate_image")
    @patch("app.services.asset_integration_service.get_candidates")
    def test_no_render_profile_omits_aspect_ratio_kwarg(
        self, mock_get_candidates, mock_generate_image,
    ):
        # 하위 호환 - render_profile을 안 넘기면 aspect_ratio kwarg
        # 자체가 generate_image 호출에 추가되지 않는다(기존 호출부와
        # 기존 mock 전부 영향받지 않음).
        mock_get_candidates.return_value = []

        def _side_effect_without_aspect_ratio(
            image_prompt, output_file, channel="wellbeing",
            is_hook_scene=False, visual_type=None,
        ):
            with open(output_file, "wb") as f:
                f.write(b"ai bytes")
            return output_file

        mock_generate_image.side_effect = _side_effect_without_aspect_ratio

        scene = {**SAMPLE_SCENE, "visual_type": "ai"}
        integrate_asset(scene, self.project_path)

        _, kwargs = mock_generate_image.call_args
        self.assertNotIn("aspect_ratio", kwargs)


if __name__ == "__main__":
    unittest.main()
