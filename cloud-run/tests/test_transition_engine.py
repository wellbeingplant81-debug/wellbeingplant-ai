import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.transition_engine import (
    HOOK_TRANSITION,
    NORMAL_TRANSITION,
    assign_transition,
    annotate_scenes_with_transitions,
)


class TestAssignTransition(unittest.TestCase):

    def test_hook_scene_gets_hook_transition(self):
        self.assertEqual(assign_transition(1), HOOK_TRANSITION)

    def test_middle_scene_gets_normal_transition(self):
        self.assertEqual(assign_transition(2), NORMAL_TRANSITION)

    def test_last_scene_gets_normal_transition(self):
        # 규칙은 hook(1번)과 그 외 두 종류뿐 - 마지막 scene도 일반
        # 전환을 사용한다 (별도 규칙 없음).
        self.assertEqual(assign_transition(6), NORMAL_TRANSITION)


class TestAnnotateScenesWithTransitions(unittest.TestCase):

    def test_each_scene_gets_a_transition_field(self):
        scenes = [{"scene": 1}, {"scene": 2}, {"scene": 3}]
        result = annotate_scenes_with_transitions(scenes)

        self.assertEqual(result[0]["transition"], HOOK_TRANSITION)
        self.assertEqual(result[1]["transition"], NORMAL_TRANSITION)
        self.assertEqual(result[2]["transition"], NORMAL_TRANSITION)

    def test_original_scenes_not_mutated(self):
        scenes = [{"scene": 1}, {"scene": 2}]
        scenes_copy = [dict(s) for s in scenes]

        annotate_scenes_with_transitions(scenes_copy)

        self.assertEqual(scenes_copy, scenes)
        self.assertNotIn("transition", scenes_copy[0])

    def test_other_fields_preserved(self):
        scenes = [{"scene": 1, "narration": "n1"}, {"scene": 2, "narration": "n2"}]
        result = annotate_scenes_with_transitions(scenes)

        self.assertEqual(result[0]["narration"], "n1")
        self.assertEqual(result[1]["narration"], "n2")

    def test_empty_scene_list_returns_empty(self):
        self.assertEqual(annotate_scenes_with_transitions([]), [])


if __name__ == "__main__":
    unittest.main()
