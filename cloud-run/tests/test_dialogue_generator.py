import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.dialogue_context_builder import DialogueContextBuilder
from app.services.dialogue_generator import (
    DialogueGenerator,
    DialogueScript,
    DialogueTurn,
)
from app.services.topic_intelligence_service import TopicIntelligenceService


class TestGenerateDialogue(unittest.TestCase):

    def setUp(self):
        topic = "당뇨병 관리법"
        topic_profile = TopicIntelligenceService.build_topic_profile(topic)
        self.context = DialogueContextBuilder.build_dialogue_context(
            topic, topic_profile,
        )

    def test_generate_dialogue_returns_dialogue_script(self):
        script = DialogueGenerator.generate_dialogue(self.context)

        self.assertIsInstance(script, DialogueScript)
        self.assertEqual(script.topic, self.context.topic)

    def test_dialogue_script_contains_turns(self):
        script = DialogueGenerator.generate_dialogue(self.context)

        self.assertIsInstance(script.turns, list)
        self.assertGreater(len(script.turns), 0)

    def test_turn_has_speaker(self):
        script = DialogueGenerator.generate_dialogue(self.context)

        for turn in script.turns:
            self.assertIsInstance(turn, DialogueTurn)
            self.assertTrue(turn.speaker)

    def test_turn_has_purpose(self):
        script = DialogueGenerator.generate_dialogue(self.context)

        for turn in script.turns:
            self.assertTrue(turn.purpose)

    def test_turn_has_text(self):
        script = DialogueGenerator.generate_dialogue(self.context)

        for turn in script.turns:
            self.assertTrue(turn.text)

    def test_default_contains_two_speakers(self):
        script = DialogueGenerator.generate_dialogue(self.context)

        speakers = {turn.speaker for turn in script.turns}

        self.assertIn("professor", speakers)
        self.assertIn("middle_aged_male", speakers)


if __name__ == "__main__":
    unittest.main()
