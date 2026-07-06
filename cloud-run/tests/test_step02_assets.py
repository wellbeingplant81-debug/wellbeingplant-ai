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


def _fake_integrate_asset(scene, project_path, channel="wellbeing", prefer_ai=False):
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


if __name__ == "__main__":
    unittest.main()
