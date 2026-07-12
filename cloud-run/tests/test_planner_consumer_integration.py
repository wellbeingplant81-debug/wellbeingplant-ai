import dataclasses
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.asset_planner import plan_asset_strategy
from app.services.dialogue_context_builder import DialogueContextBuilder
from app.services.dialogue_generator import DialogueGenerator
from app.services.planner_consumer_integration import PlannerConsumerIntegration
from app.services.planner_context_builder import (
    build_planner_context as legacy_build_planner_context,
)
from app.services.planner_dialogue_adapter import PlannerDialogueAdapter
from app.services.topic_intelligence_service import TopicIntelligenceService


SIX_SCENES = [
    {"scene": i, "narration": f"n{i}", "image_prompt": f"p{i}"}
    for i in range(1, 7)
]


class TestPlannerConsumerIntegration(unittest.TestCase):
    """
    Sprint87 - Feature Flag(PlannerDialogueInput.enabled) OFF면 기존
    scenes 기반 Planner 경로(planner_context_builder.build_planner_
    context())를 그대로 쓰고, ON이면 PlannerDialogueInput(Sprint86)을
    쓴다. 기존 Planner(asset_planner.py) 구현은 수정하지 않는다 - 이
    통합 계층은 어떤 입력을 쓸지만 정한다.
    """

    def setUp(self):
        self.asset_plan = plan_asset_strategy(SIX_SCENES)

        topic = "당뇨병 관리법"
        topic_profile = TopicIntelligenceService.build_topic_profile(topic)
        context = DialogueContextBuilder.build_dialogue_context(
            topic, topic_profile,
        )
        dialogue_script = DialogueGenerator.generate_dialogue(context)

        self.disabled_input = PlannerDialogueAdapter.build(
            dialogue_script, topic_profile,
        )
        # PlannerDialogueAdapter.build()는 enabled를 항상 False로
        # 고정하므로(Sprint86), 활성화된 입력은 테스트에서 직접 만든다.
        self.enabled_input = dataclasses.replace(self.disabled_input, enabled=True)

    def test_build_planner_context_with_dialogue_disabled(self):
        result = PlannerConsumerIntegration.build_planner_context(
            self.asset_plan, dialogue_input=self.disabled_input,
        )

        expected = legacy_build_planner_context(self.asset_plan)

        self.assertEqual(result, expected)

    def test_build_planner_context_with_dialogue_enabled(self):
        result = PlannerConsumerIntegration.build_planner_context(
            self.asset_plan, dialogue_input=self.enabled_input,
        )

        self.assertIsNotNone(result)
        self.assertIn("dialogue_script", result)

    def test_existing_planner_path_unchanged(self):
        result = PlannerConsumerIntegration.build_planner_context(self.asset_plan)

        expected = legacy_build_planner_context(self.asset_plan)

        self.assertEqual(result, expected)

    def test_dialogue_path_preserves_scene_count(self):
        result = PlannerConsumerIntegration.build_planner_context(
            self.asset_plan, dialogue_input=self.enabled_input,
        )

        self.assertEqual(
            len(result["dialogue_script"].turns),
            len(self.enabled_input.dialogue_script.turns),
        )

    def test_feature_flag_default_off(self):
        # dialogue_input을 아예 넘기지 않아도(기본값) 기존 경로여야 한다.
        result = PlannerConsumerIntegration.build_planner_context(self.asset_plan)

        expected = legacy_build_planner_context(self.asset_plan)

        self.assertEqual(result, expected)

    def test_planner_context_uses_dialogue_input_when_enabled(self):
        result = PlannerConsumerIntegration.build_planner_context(
            self.asset_plan, dialogue_input=self.enabled_input,
        )

        self.assertEqual(result["dialogue_script"], self.enabled_input.dialogue_script)
        self.assertEqual(result["topic_profile"], self.enabled_input.topic_profile)


if __name__ == "__main__":
    unittest.main()
