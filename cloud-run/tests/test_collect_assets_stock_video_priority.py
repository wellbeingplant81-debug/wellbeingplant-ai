"""
Sprint121 - Stock Video Priority. collect_assets()가
config.ENABLE_STOCK_VIDEO_PRIORITY일 때, 이미 확정된 scene["visual_type"]
을 그대로 신뢰해 Real scene에 Stock Video 우선(asset_strategy="upload"
스코어링/관련성 체크 메커니즘 재사용 + prefer_video=True)을 적용하되,
UploadAssetStrategy.select_asset_mode()(AI/Real 재분류 로직)는 절대
호출하지 않는지 확인한다.

핵심 회귀 방지: 이 Sprint는 "무엇을 보여줄지"(AI/Real Planning)는
절대 바꾸지 않고 "어떻게 표현할지"(Stock Video vs Stock Image)만
개선한다. Feature Flag 기본값(False)에서는 기존 동작과 100% 동일해야
한다(Regression Zero).
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
    {"scene": 1, "narration": "n1", "image_prompt": "p1", "visual_type": "real"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2", "visual_type": "ai"},
    {"scene": 3, "narration": "n3", "image_prompt": "p3", "visual_type": "real"},
]


def _fake_integrate_asset(
    scene, project_path, channel="wellbeing", prefer_ai=False, visual_profile=None,
    asset_strategy=None, prefer_video=False, max_assets=None,
):
    enriched = dict(scene)
    enriched["asset_path"] = f"{project_path}/images/scene{scene['scene']}.png"
    enriched["provider"] = "ai_image" if prefer_ai else "pexels_video"
    enriched["asset_type"] = "image" if prefer_ai else "video"
    enriched["search_query"] = "query"
    enriched["confidence"] = 1.0
    return enriched


class _FlagTestCase(unittest.TestCase):

    def setUp(self):
        self._original_flag = config.ENABLE_STOCK_VIDEO_PRIORITY
        self.addCleanup(setattr, config, "ENABLE_STOCK_VIDEO_PRIORITY", self._original_flag)


class TestStockVideoPriorityFlagOffIsRegressionSafe(_FlagTestCase):

    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_flag_off_omits_asset_strategy_and_prefer_video_kwargs(
        self, mock_integrate, mock_select_ai_priority,
    ):
        config.ENABLE_STOCK_VIDEO_PRIORITY = False

        collect_assets(SAMPLE_SCENES, "output/proj")

        for call in mock_integrate.call_args_list:
            self.assertNotIn("asset_strategy", call.kwargs)
            self.assertNotIn("prefer_video", call.kwargs)


class TestStockVideoPriorityFlagOnAppliesToRealScenesOnly(_FlagTestCase):

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_real_scenes_get_stock_video_priority_wiring(
        self, mock_integrate, mock_select_asset_mode,
    ):
        config.ENABLE_STOCK_VIDEO_PRIORITY = True

        collect_assets(SAMPLE_SCENES, "output/proj")

        by_scene = {
            call.args[0]["scene"]: call.kwargs
            for call in mock_integrate.call_args_list
        }

        self.assertEqual(by_scene[1]["asset_strategy"], "upload")
        self.assertTrue(by_scene[1]["prefer_video"])
        self.assertFalse(by_scene[1].get("prefer_ai", False))

        self.assertEqual(by_scene[3]["asset_strategy"], "upload")
        self.assertTrue(by_scene[3]["prefer_video"])
        self.assertFalse(by_scene[3].get("prefer_ai", False))

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_ai_scene_visual_type_is_trusted_not_reclassified(
        self, mock_integrate, mock_select_asset_mode,
    ):
        # 핵심 회귀 방지 테스트: UploadAssetStrategy.select_asset_mode()
        # (AI/Real 재분류 로직)가 절대 호출되지 않아야 하고, scene 2의
        # prefer_ai는 오직 scene["visual_type"] == "ai"라는 이미 확정된
        # 값에서만 나와야 한다.
        config.ENABLE_STOCK_VIDEO_PRIORITY = True

        collect_assets(SAMPLE_SCENES, "output/proj")

        mock_select_asset_mode.assert_not_called()

        by_scene = {
            call.args[0]["scene"]: call.kwargs.get("prefer_ai")
            for call in mock_integrate.call_args_list
        }
        self.assertTrue(by_scene[2])


class TestStockVideoPriorityDoesNotInterfereWithExplicitUploadStrategy(_FlagTestCase):

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_explicit_asset_strategy_upload_takes_existing_path_unchanged(
        self, mock_integrate, mock_select_asset_mode,
    ):
        # 호출자가 명시적으로 asset_strategy="upload"를 넘기면(실제
        # ProductionProfile "upload" 경로), Sprint121 플래그가 켜져
        # 있어도 기존 UploadAssetStrategy.select_asset_mode() 재분류
        # 경로를 그대로 타야 한다(기존 동작 변경 금지).
        config.ENABLE_STOCK_VIDEO_PRIORITY = True
        mock_select_asset_mode.return_value = None

        collect_assets(SAMPLE_SCENES, "output/proj", asset_strategy="upload")

        mock_select_asset_mode.assert_called()


if __name__ == "__main__":
    unittest.main()
