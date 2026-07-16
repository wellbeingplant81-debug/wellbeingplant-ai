"""
Sprint121 - Scene Stability. collect_assets()가 config.ENABLE_SCENE_
ASSET_LIMIT일 때, scene마다 narration 예상 길이(duration_estimator)를
scene_stability_policy.max_assets_for_duration()에 넘겨 max_assets를
계산해 integrate_asset()에 전달하는지 확인한다.

max_assets는 primary asset이 실제로 AI 생성일 때만(_generate_extra_
ai_assets) 영향을 준다 - Stock(Real) scene은 원래도 asset 1개뿐이라
이 값과 무관하다(기존 Sprint62-4 불변식, 이 Sprint에서 건드리지 않음).

Motion Contract가 이미 max_assets를 정한 scene(기존 asset_strategy=
"upload" + ENABLE_MOTION_CONTRACT 경로)은 이 정책이 덮어쓰지 않는다
(회귀 방지).
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app import config
from app.steps.step02_assets import collect_assets


SAMPLE_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1", "visual_type": "ai"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2", "visual_type": "ai"},
    {"scene": 3, "narration": "n3", "image_prompt": "p3", "visual_type": "ai"},
]


def _fake_integrate_asset(
    scene, project_path, channel="wellbeing", prefer_ai=False, visual_profile=None,
    asset_strategy=None, prefer_video=False, max_assets=None,
):
    enriched = dict(scene)
    enriched["asset_path"] = f"{project_path}/images/scene{scene['scene']}.png"
    enriched["provider"] = "ai_image"
    enriched["asset_type"] = "image"
    enriched["search_query"] = "query"
    enriched["confidence"] = 1.0
    return enriched


def _fake_estimate_duration(narration):
    # scene 번호를 narration 문자열에 그대로 인코딩해 결정적으로
    # 서로 다른 duration 구간을 흉내낸다.
    return {"n1": 3.0, "n2": 6.0, "n3": 10.0}[narration]


class _FlagTestCase(unittest.TestCase):

    def setUp(self):
        self._original_flag = config.ENABLE_SCENE_ASSET_LIMIT
        self.addCleanup(setattr, config, "ENABLE_SCENE_ASSET_LIMIT", self._original_flag)


class TestSceneAssetLimitFlagOffIsRegressionSafe(_FlagTestCase):

    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_flag_off_omits_max_assets_kwarg(
        self, mock_integrate, mock_select_ai_priority,
    ):
        config.ENABLE_SCENE_ASSET_LIMIT = False

        collect_assets(SAMPLE_SCENES, "output/proj")

        for call in mock_integrate.call_args_list:
            self.assertNotIn("max_assets", call.kwargs)


class TestSceneAssetLimitFlagOnAppliesDurationBasedCap(_FlagTestCase):

    @patch(
        "app.steps.step02_assets.duration_estimator.estimate_duration",
        side_effect=_fake_estimate_duration,
    )
    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_max_assets_computed_from_estimated_scene_duration(
        self, mock_integrate, mock_select_ai_priority, mock_estimate_duration,
    ):
        config.ENABLE_SCENE_ASSET_LIMIT = True

        collect_assets(SAMPLE_SCENES, "output/proj")

        by_scene = {
            call.args[0]["scene"]: call.kwargs.get("max_assets")
            for call in mock_integrate.call_args_list
        }

        self.assertEqual(by_scene[1], 1)  # 3.0초 -> 0~5초 구간 -> 1
        self.assertEqual(by_scene[2], 2)  # 6.0초 -> 5~8초 구간 -> 2
        self.assertEqual(by_scene[3], 3)  # 10.0초 -> 8초 이상 -> 3


class TestSceneAssetLimitDoesNotOverrideMotionContract(_FlagTestCase):

    @patch("app.services.motion_contract.build_motion_contract")
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_motion_contract_max_assets_takes_priority(
        self, mock_integrate, mock_build_contract,
    ):
        original_motion_flag = config.ENABLE_MOTION_CONTRACT
        config.ENABLE_MOTION_CONTRACT = True
        self.addCleanup(setattr, config, "ENABLE_MOTION_CONTRACT", original_motion_flag)
        config.ENABLE_SCENE_ASSET_LIMIT = True

        mock_build_contract.return_value = [
            {
                "scene_id": 1, "motion": "dynamic", "max_assets": 4,
                "video_intent": {"intent": "preferred_image"},
            },
        ]

        collect_assets(
            [{"scene": 1, "narration": "n1", "image_prompt": "p1", "visual_type": "ai"}],
            "output/proj",
            asset_strategy="upload",
        )

        call = mock_integrate.call_args_list[0]
        # Motion Contract가 이미 max_assets=4를 정했으므로 Scene
        # Stability(duration 기반) 값으로 덮어쓰지 않는다.
        self.assertEqual(call.kwargs.get("max_assets"), 4)


if __name__ == "__main__":
    unittest.main()
