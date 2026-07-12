"""
Sprint96 (RED) - step02_assets.collect_assets()의 asset_strategy override.

collect_assets()에 optional 파라미터 asset_strategy=None을 추가한다.
asset_plan이 있으면(기존 Sprint77 우선순위) asset_strategy는 완전히
무시된다. asset_plan이 없을 때: asset_strategy가 None/"default"/그 외
값이면 지금까지처럼 select_ai_priority_scenes()로 배치 전체 AI 우선
후보를 계산하고(UploadAssetStrategy 미호출), asset_strategy="upload"면
scene마다 UploadAssetStrategy.select_asset_mode()를 호출해 prefer_ai를
정한다(select_ai_priority_scenes 미호출). asset_priority_classifier.py/
asset_integration_service.py/upload_asset_strategy.py는 이번 스프린트에서
전혀 수정하지 않는다 - upload_asset_strategy.UploadAssetStrategy는 호출
Activation 대상으로만 쓴다. 아직 구현이 없으므로(RED) asset_strategy
관련 테스트는 실패해야 정상이다.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.steps.step02_assets import collect_assets


SAMPLE_SCENES = [
    {"scene": 1, "narration": "n1", "image_prompt": "p1"},
    {"scene": 2, "narration": "n2", "image_prompt": "p2"},
]


def _fake_integrate_asset(
    scene, project_path, channel="wellbeing", prefer_ai=False, visual_profile=None,
    asset_strategy=None,
):
    enriched = dict(scene)
    enriched["asset_path"] = f"{project_path}/images/scene{scene['scene']}.png"
    enriched["provider"] = "ai_image"
    enriched["asset_type"] = "image"
    enriched["search_query"] = "query"
    enriched["confidence"] = 1.0
    return enriched


class TestStep02AssetsAssetStrategyOverride(unittest.TestCase):

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_no_asset_strategy_uses_existing_ai_priority_selection(
        self, mock_integrate, mock_select_ai_priority, mock_upload_strategy,
    ):
        collect_assets(SAMPLE_SCENES, "output/proj")

        mock_select_ai_priority.assert_called_once()
        mock_upload_strategy.assert_not_called()

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_default_asset_strategy_uses_existing_ai_priority_selection(
        self, mock_integrate, mock_select_ai_priority, mock_upload_strategy,
    ):
        collect_assets(SAMPLE_SCENES, "output/proj", asset_strategy="default")

        mock_select_ai_priority.assert_called_once()
        mock_upload_strategy.assert_not_called()

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_upload_asset_strategy_uses_upload_asset_strategy_per_scene(
        self, mock_integrate, mock_select_ai_priority, mock_upload_strategy,
    ):
        from app.services.upload_asset_strategy import AssetMode
        mock_upload_strategy.return_value = AssetMode.AI

        collect_assets(SAMPLE_SCENES, "output/proj", asset_strategy="upload")

        self.assertEqual(mock_upload_strategy.call_count, len(SAMPLE_SCENES))
        mock_select_ai_priority.assert_not_called()

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_asset_plan_takes_precedence_over_asset_strategy(
        self, mock_integrate, mock_select_ai_priority, mock_upload_strategy,
    ):
        asset_plan = {
            1: {"scene": 1, "prefer_ai": True, "visual_profile": {
                "camera_distance": "wide", "camera_angle": "eye level",
                "composition": "centered", "lighting": "soft daylight",
            }},
            2: {"scene": 2, "prefer_ai": False, "visual_profile": {
                "camera_distance": "medium", "camera_angle": "low angle",
                "composition": "rule of thirds", "lighting": "dramatic light",
            }},
        }

        collect_assets(
            SAMPLE_SCENES, "output/proj",
            asset_plan=asset_plan, asset_strategy="upload",
        )

        mock_upload_strategy.assert_not_called()
        mock_select_ai_priority.assert_not_called()

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_asset_strategy_upload_passed_through_to_integrate_asset(
        self, mock_integrate, mock_select_ai_priority, mock_upload_strategy,
    ):
        """Sprint96.1 (RED) - asset_strategy="upload"가 integrate_asset()
        호출까지 그대로 전달되어야 한다(asset_quality_scorer/visual_type
        충돌 해결 Hotfix가 이 값을 실제로 소비한다)."""
        from app.services.upload_asset_strategy import AssetMode
        mock_upload_strategy.return_value = AssetMode.STOCK

        collect_assets(SAMPLE_SCENES, "output/proj", asset_strategy="upload")

        for call in mock_integrate.call_args_list:
            self.assertEqual(call.kwargs.get("asset_strategy"), "upload")

    @patch("app.services.upload_asset_strategy.UploadAssetStrategy.select_asset_mode")
    @patch("app.steps.step02_assets.select_ai_priority_scenes", return_value=set())
    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_no_asset_strategy_omits_asset_strategy_kwarg_to_integrate_asset(
        self, mock_integrate, mock_select_ai_priority, mock_upload_strategy,
    ):
        """Sprint96.1 (RED) - asset_strategy 미지정이면 기존처럼
        integrate_asset()에도 asset_strategy를 넘기지 않아야 한다
        (Regression Zero)."""
        collect_assets(SAMPLE_SCENES, "output/proj")

        for call in mock_integrate.call_args_list:
            self.assertNotIn("asset_strategy", call.kwargs)


if __name__ == "__main__":
    unittest.main()
