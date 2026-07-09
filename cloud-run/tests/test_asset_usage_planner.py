import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import asset_usage_planner


class TestPlanAssetUsage(unittest.TestCase):
    """
    Sprint64-3 - Role metadata를 활용한 Asset Usage Planning. 순수
    함수 plan_asset_usage()가 scene["assets"](role 있을 수도/없을
    수도 있음)를 받아 role 가중 duration 분배와 motion_hint를
    계산한다. video_builder.py/kenburns.py는 이번 스프린트에서
    전혀 연결하지 않는다 - 여기서 검증하는 건 계획 산출물 자체뿐이다.
    """

    # --- role 4종 모두 있을 때 가중치 비율 ---

    def test_all_four_roles_present_duration_ratios_match_weights(self):
        assets = [
            {"path": "a.png", "type": "image", "role": "environment"},
            {"path": "b.png", "type": "image", "role": "subject"},
            {"path": "c.png", "type": "image", "role": "detail"},
            {"path": "d.png", "type": "image", "role": "transition"},
        ]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=8.0)

        weights = [1.2, 1.0, 0.8, 0.6]
        total_weight = sum(weights)
        expected = [8.0 * w / total_weight for w in weights]

        for entry, expected_duration in zip(plan, expected):
            self.assertAlmostEqual(entry["duration"], expected_duration, places=6)

        self.assertAlmostEqual(sum(entry["duration"] for entry in plan), 8.0, places=6)

    def test_environment_gets_longer_duration_than_transition(self):
        assets = [
            {"path": "a.png", "role": "environment"},
            {"path": "b.png", "role": "transition"},
        ]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=4.0)

        self.assertGreater(plan[0]["duration"], plan[1]["duration"])

    # --- role이 전혀 없으면 균등 분배와 동일(하위 호환) ---

    def test_no_role_falls_back_to_equal_split(self):
        assets = [
            {"path": "a.png", "type": "image"},
            {"path": "b.png", "type": "image"},
            {"path": "c.png", "type": "image"},
            {"path": "d.png", "type": "image"},
        ]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=8.0)

        for entry in plan:
            self.assertAlmostEqual(entry["duration"], 2.0, places=6)

    # --- 일부만 role, 나머지는 기본 가중치 ---

    def test_partial_role_uses_default_weight_for_missing(self):
        assets = [
            {"path": "a.png", "role": "environment"},  # weight 1.2
            {"path": "b.png"},                          # weight 기본 1.0
        ]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=4.4)

        total_weight = 1.2 + 1.0
        self.assertAlmostEqual(plan[0]["duration"], 4.4 * 1.2 / total_weight, places=6)
        self.assertAlmostEqual(plan[1]["duration"], 4.4 * 1.0 / total_weight, places=6)

    # --- 알 수 없는 role 문자열도 안전하게 처리 ---

    def test_unknown_role_string_uses_default_weight(self):
        assets = [
            {"path": "a.png", "role": "totally_unknown_role"},
            {"path": "b.png", "role": "subject"},
        ]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=2.0)

        # 둘 다 weight 1.0(기본값/subject)으로 동일하게 취급되어야 한다.
        self.assertAlmostEqual(plan[0]["duration"], plan[1]["duration"], places=6)

    # --- motion_hint 매핑 ---

    def test_motion_hint_mapping_for_each_role(self):
        assets = [
            {"path": "a.png", "role": "environment"},
            {"path": "b.png", "role": "subject"},
            {"path": "c.png", "role": "detail"},
            {"path": "d.png", "role": "transition"},
        ]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=8.0)

        expected_hints = ["zoom_out", "zoom_in", "static_pan", "pan_horizontal"]
        self.assertEqual([entry["motion_hint"] for entry in plan], expected_hints)

    def test_motion_hint_default_for_missing_role(self):
        assets = [{"path": "a.png"}]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=5.0)

        self.assertEqual(plan[0]["motion_hint"], "auto")

    def test_motion_hint_default_for_unknown_role(self):
        assets = [{"path": "a.png", "role": "something_new"}]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=5.0)

        self.assertEqual(plan[0]["motion_hint"], "auto")

    # --- 엣지 케이스 ---

    def test_empty_assets_returns_empty_list(self):
        self.assertEqual(asset_usage_planner.plan_asset_usage([], scene_duration=8.0), [])

    def test_single_asset_gets_full_scene_duration(self):
        assets = [{"path": "a.png", "role": "subject"}]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=6.5)

        self.assertEqual(len(plan), 1)
        self.assertAlmostEqual(plan[0]["duration"], 6.5, places=6)

    def test_path_and_role_passthrough_unchanged(self):
        assets = [{"path": "custom/path/a.png", "type": "image", "role": "detail"}]

        plan = asset_usage_planner.plan_asset_usage(assets, scene_duration=3.0)

        self.assertEqual(plan[0]["path"], "custom/path/a.png")
        self.assertEqual(plan[0]["role"], "detail")

    def test_does_not_mutate_input_assets_list(self):
        assets = [{"path": "a.png", "role": "environment"}]
        assets_copy = [dict(asset) for asset in assets]

        asset_usage_planner.plan_asset_usage(assets, scene_duration=4.0)

        self.assertEqual(assets, assets_copy)


if __name__ == "__main__":
    unittest.main()
