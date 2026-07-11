import os
import sys
import time
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
    {"scene": 3, "narration": "n3", "image_prompt": "p3"},
]


def _fake_integrate_asset(
    scene, project_path, channel="wellbeing", prefer_ai=False, visual_profile=None,
):
    # scene 번호가 클수록 늦게 끝나도록 지연을 줘서 as_completed 순서가
    # 입력 순서와 다를 수 있음을 시뮬레이션한다.
    time.sleep(0.01 * (len(SAMPLE_SCENES) - scene["scene"]))
    enriched = dict(scene)
    enriched["asset_path"] = f"{project_path}/images/scene{scene['scene']}.png"
    enriched["provider"] = "ai_image"
    enriched["asset_type"] = "image"
    enriched["search_query"] = "query"
    enriched["confidence"] = 1.0
    return enriched


class TestStep02Assets(unittest.TestCase):

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_returns_all_scenes_sorted_by_scene_number(self, mock_integrate):
        results = collect_assets(SAMPLE_SCENES, "output/proj")

        self.assertEqual([r["scene"] for r in results], [1, 2, 3])

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_calls_integrate_asset_once_per_scene(self, mock_integrate):
        collect_assets(SAMPLE_SCENES, "output/proj")

        self.assertEqual(mock_integrate.call_count, 3)

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_project_path_and_channel_passed_through(self, mock_integrate):
        collect_assets(SAMPLE_SCENES, "output/proj", channel="foodbeat")

        for call in mock_integrate.call_args_list:
            args, kwargs = call
            self.assertEqual(args[1], "output/proj")
            self.assertEqual(args[2], "foodbeat")

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_default_channel_is_wellbeing(self, mock_integrate):
        collect_assets(SAMPLE_SCENES, "output/proj")

        for call in mock_integrate.call_args_list:
            args, kwargs = call
            self.assertEqual(args[2], "wellbeing")

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_enriched_fields_present_in_results(self, mock_integrate):
        results = collect_assets(SAMPLE_SCENES, "output/proj")

        for result in results:
            self.assertIn("asset_path", result)
            self.assertIn("provider", result)
            self.assertIn("asset_type", result)
            self.assertIn("search_query", result)
            self.assertIn("confidence", result)
            # 기존 필드도 보존되어야 한다
            self.assertIn("narration", result)
            self.assertIn("image_prompt", result)

    @patch("app.steps.step02_assets.integrate_asset")
    def test_single_scene_failure_propagates(self, mock_integrate):
        mock_integrate.side_effect = Exception("boom")

        with self.assertRaises(Exception):
            collect_assets(SAMPLE_SCENES, "output/proj")

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_prefer_ai_threaded_through_for_ai_priority_scene(self, mock_integrate):
        # Sprint38 - Hybrid Asset Engine: 명확한 의료/인물 키워드가 있는
        # scene만 prefer_ai=True로 넘어가야 하고, 나머지는 False여야 한다.
        scenes = [
            {
                "scene": 1,
                "narration": "혈관과 세포 이야기",
                "image_prompt": "diagram of blood vessel anatomy",
            },
            {"scene": 2, "narration": "n2", "image_prompt": "p2"},
            {"scene": 3, "narration": "n3", "image_prompt": "p3"},
        ]

        collect_assets(scenes, "output/proj")

        prefer_ai_by_scene = {
            call.args[0]["scene"]: call.kwargs["prefer_ai"]
            for call in mock_integrate.call_args_list
        }

        self.assertTrue(prefer_ai_by_scene[1])
        self.assertFalse(prefer_ai_by_scene[2])
        self.assertFalse(prefer_ai_by_scene[3])

    # --- Sprint72-1: Visual Diversity Engine wiring ---

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_visual_profile_passed_for_every_scene(self, mock_integrate):
        collect_assets(SAMPLE_SCENES, "output/proj")

        for call in mock_integrate.call_args_list:
            self.assertIsNotNone(call.kwargs["visual_profile"])

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_different_scenes_get_different_visual_profiles(self, mock_integrate):
        collect_assets(SAMPLE_SCENES, "output/proj")

        profiles_by_scene = {
            call.args[0]["scene"]: call.kwargs["visual_profile"]
            for call in mock_integrate.call_args_list
        }

        combos = {
            (p["camera_distance"], p["camera_angle"])
            for p in profiles_by_scene.values()
        }
        self.assertEqual(len(combos), len(SAMPLE_SCENES))

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_visual_profile_matches_assign_visual_profiles(self, mock_integrate):
        from app.services.visual_diversity_engine import assign_visual_profiles

        collect_assets(SAMPLE_SCENES, "output/proj")

        expected = assign_visual_profiles(SAMPLE_SCENES)

        for call in mock_integrate.call_args_list:
            scene_number = call.args[0]["scene"]
            self.assertEqual(call.kwargs["visual_profile"], expected[scene_number])

    # --- Sprint77: Asset Planner v1 wiring ---

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_asset_plan_none_matches_pre_sprint77_behavior(self, mock_integrate):
        # asset_plan을 안 넘기면(기본값 None) 기존처럼 select_ai_priority_
        # scenes()/assign_visual_profiles()를 직접 계산한 결과와 완전히
        # 동일해야 한다 - 하위 호환의 핵심 검증.
        from app.services.visual_diversity_engine import assign_visual_profiles

        collect_assets(SAMPLE_SCENES, "output/proj")

        expected_profiles = assign_visual_profiles(SAMPLE_SCENES)

        for call in mock_integrate.call_args_list:
            scene_number = call.args[0]["scene"]
            self.assertEqual(call.kwargs["visual_profile"], expected_profiles[scene_number])
            self.assertFalse(call.kwargs["prefer_ai"])

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_asset_plan_provided_overrides_prefer_ai(self, mock_integrate):
        asset_plan = {
            1: {"scene": 1, "prefer_ai": True, "visual_profile": {
                "camera_distance": "wide", "camera_angle": "eye level",
                "composition": "centered", "lighting": "soft daylight",
            }},
            2: {"scene": 2, "prefer_ai": False, "visual_profile": {
                "camera_distance": "medium", "camera_angle": "low angle",
                "composition": "rule of thirds", "lighting": "dramatic light",
            }},
            3: {"scene": 3, "prefer_ai": False, "visual_profile": {
                "camera_distance": "close-up", "camera_angle": "high angle",
                "composition": "foreground framing", "lighting": "warm indoor",
            }},
        }

        collect_assets(SAMPLE_SCENES, "output/proj", asset_plan=asset_plan)

        prefer_ai_by_scene = {
            call.args[0]["scene"]: call.kwargs["prefer_ai"]
            for call in mock_integrate.call_args_list
        }

        self.assertTrue(prefer_ai_by_scene[1])
        self.assertFalse(prefer_ai_by_scene[2])
        self.assertFalse(prefer_ai_by_scene[3])

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_asset_plan_provided_overrides_visual_profile(self, mock_integrate):
        asset_plan = {
            1: {"scene": 1, "prefer_ai": False, "visual_profile": {
                "camera_distance": "macro", "camera_angle": "top-down",
                "composition": "leading lines", "lighting": "backlit",
            }},
            2: {"scene": 2, "prefer_ai": False, "visual_profile": {
                "camera_distance": "medium", "camera_angle": "low angle",
                "composition": "rule of thirds", "lighting": "dramatic light",
            }},
            3: {"scene": 3, "prefer_ai": False, "visual_profile": {
                "camera_distance": "close-up", "camera_angle": "high angle",
                "composition": "foreground framing", "lighting": "warm indoor",
            }},
        }

        collect_assets(SAMPLE_SCENES, "output/proj", asset_plan=asset_plan)

        profile_scene_1 = next(
            call.kwargs["visual_profile"]
            for call in mock_integrate.call_args_list
            if call.args[0]["scene"] == 1
        )

        self.assertEqual(profile_scene_1["camera_distance"], "macro")

    @patch("app.steps.step02_assets.integrate_asset", side_effect=_fake_integrate_asset)
    def test_empty_asset_plan_falls_back_to_existing_computation(self, mock_integrate):
        # asset_plan={}(falsy)도 None과 동일하게 기존 경로로 폴백해야 한다.
        from app.services.visual_diversity_engine import assign_visual_profiles

        collect_assets(SAMPLE_SCENES, "output/proj", asset_plan={})

        expected_profiles = assign_visual_profiles(SAMPLE_SCENES)

        for call in mock_integrate.call_args_list:
            scene_number = call.args[0]["scene"]
            self.assertEqual(call.kwargs["visual_profile"], expected_profiles[scene_number])


if __name__ == "__main__":
    unittest.main()
