import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.dialogue_context_builder import DialogueContextBuilder
from app.services.dialogue_generator import DialogueGenerator
from app.services.planner_dialogue_adapter import (
    PlannerDialogueAdapter,
    PlannerDialogueInput,
)
from app.services.topic_intelligence_service import TopicIntelligenceService


class TestBuildPlannerInput(unittest.TestCase):

    def setUp(self):
        topic = "당뇨병 관리법"
        self.topic_profile = TopicIntelligenceService.build_topic_profile(topic)
        context = DialogueContextBuilder.build_dialogue_context(
            topic, self.topic_profile,
        )
        self.dialogue_script = DialogueGenerator.generate_dialogue(context)

    def test_build_planner_input_returns_planner_input(self):
        result = PlannerDialogueAdapter.build(
            self.dialogue_script, self.topic_profile,
        )

        self.assertIsInstance(result, PlannerDialogueInput)

    def test_contains_dialogue_script(self):
        result = PlannerDialogueAdapter.build(
            self.dialogue_script, self.topic_profile,
        )

        self.assertEqual(result.dialogue_script, self.dialogue_script)

    def test_contains_topic_profile(self):
        result = PlannerDialogueAdapter.build(
            self.dialogue_script, self.topic_profile,
        )

        self.assertEqual(result.topic_profile, self.topic_profile)

    def test_contains_planner_hints(self):
        result = PlannerDialogueAdapter.build(
            self.dialogue_script, self.topic_profile,
        )

        self.assertEqual(result.planner_hints, self.topic_profile.planner_hints)

    def test_preserves_scene_count(self):
        result = PlannerDialogueAdapter.build(
            self.dialogue_script, self.topic_profile,
        )

        self.assertEqual(
            len(result.dialogue_script.turns), len(self.dialogue_script.turns),
        )

    def test_default_flag_disabled(self):
        result = PlannerDialogueAdapter.build(
            self.dialogue_script, self.topic_profile,
        )

        self.assertFalse(result.enabled)


if __name__ == "__main__":
    unittest.main()
