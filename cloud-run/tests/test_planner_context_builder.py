import copy
import json
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_planner import plan_asset_strategy
from app.services.planner_context_builder import build_planner_context


SIX_SCENES = [
    {"scene": i, "narration": f"n{i}", "image_prompt": f"p{i}"}
    for i in range(1, 7)
]

# 실제 plan_asset_strategy() 출력(scene/prefer_ai/visual_profile/
# scene_role/scene_shot/scene_intent가 전부 채워진 형태)을 그대로
# fixture로 쓴다 - Consumer Interface가 실제 Planner 출력 구조와
# 어긋나지 않는지 확인하기 위함이다.
SAMPLE_ASSET_PLAN = plan_asset_strategy(SIX_SCENES)


class TestBuildPlannerContextOff(unittest.TestCase):
    """
    Sprint81 - Planner가 꺼져 있으면(asset_plan이 없음/빈 dict) 소비자
    쪽에서 "Planner 정보 없음"을 명확히 구분할 수 있어야 하므로 None을
    반환한다. 기존 Prompt 생성 로직은 이 모듈을 아직 전혀 참조하지
    않지만(이번 Sprint는 인터페이스만 구축), 향후 소비자가 이 None을
    보고 기존 동작(Planner 없이 생성)으로 그대로 폴백할 수 있게
    하는 것이 이 계약의 목적이다.
    """

    def test_none_asset_plan_returns_none(self):
        self.assertIsNone(build_planner_context(None))

    def test_empty_asset_plan_returns_none(self):
        self.assertIsNone(build_planner_context({}))


class TestBuildPlannerContextOn(unittest.TestCase):

    def test_returns_context_when_asset_plan_present(self):
        context = build_planner_context(SAMPLE_ASSET_PLAN)

        self.assertIsNotNone(context)

    def test_context_contains_scene_data(self):
        context = build_planner_context(SAMPLE_ASSET_PLAN)

        self.assertIn("scenes", context)
        self.assertEqual(context["scenes"], SAMPLE_ASSET_PLAN)

    def test_result_is_json_serializable(self):
        context = build_planner_context(SAMPLE_ASSET_PLAN)

        json.dumps(context)

    def test_does_not_mutate_input_asset_plan(self):
        plan_copy = copy.deepcopy(SAMPLE_ASSET_PLAN)

        build_planner_context(SAMPLE_ASSET_PLAN)

        self.assertEqual(SAMPLE_ASSET_PLAN, plan_copy)

    def test_is_pure_and_deterministic(self):
        first = build_planner_context(SAMPLE_ASSET_PLAN)
        second = build_planner_context(SAMPLE_ASSET_PLAN)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
