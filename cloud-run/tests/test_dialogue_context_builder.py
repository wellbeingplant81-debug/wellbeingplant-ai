import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.dialogue_context_builder import (
    DialogueContext,
    DialogueContextBuilder,
)
from app.services.topic_intelligence_service import TopicIntelligenceService


class TestBuildDialogueContext(unittest.TestCase):

    def setUp(self):
        self.topic = "당뇨병 관리법"
        self.topic_profile = TopicIntelligenceService.build_topic_profile(self.topic)
        self.builder = DialogueContextBuilder()

    def test_build_dialogue_context_returns_dialogue_context(self):
        context = self.builder.build_dialogue_context(self.topic, self.topic_profile)

        self.assertIsInstance(context, DialogueContext)

    def test_context_contains_topic_profile(self):
        context = self.builder.build_dialogue_context(self.topic, self.topic_profile)

        self.assertEqual(context.topic, self.topic)
        self.assertEqual(context.topic_profile, self.topic_profile)

    def test_context_contains_target_age(self):
        context = self.builder.build_dialogue_context(self.topic, self.topic_profile)

        self.assertEqual(context.target_age, self.topic_profile.target_age)

    def test_context_contains_conversation_style(self):
        context = self.builder.build_dialogue_context(self.topic, self.topic_profile)

        self.assertEqual(context.conversation_style, self.topic_profile.conversation_style)

    def test_context_contains_speakers(self):
        context = self.builder.build_dialogue_context(self.topic, self.topic_profile)

        self.assertIsInstance(context.speakers, list)
        self.assertGreaterEqual(len(context.speakers), 2)

        for speaker in context.speakers:
            self.assertIn("role", speaker)

    def test_context_contains_asset_hints(self):
        context = self.builder.build_dialogue_context(self.topic, self.topic_profile)

        self.assertEqual(context.asset_hints, self.topic_profile.asset_hints)


if __name__ == "__main__":
    unittest.main()
