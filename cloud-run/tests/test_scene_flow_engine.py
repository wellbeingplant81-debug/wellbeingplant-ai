import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.scene_flow_engine import analyze_flow, annotate_scenes_with_flow


SCENES = [
    {"scene": 1, "search_query": "morning water glass drink"},
    {"scene": 2, "search_query": "morning water digestion habit"},
    {"scene": 3, "search_query": "gut health intestine bacteria"},
]


class TestAnalyzeFlow(unittest.TestCase):

    def test_single_scene_has_no_pairs_and_perfect_score(self):
        result = analyze_flow([{"scene": 1, "search_query": "a b c"}])
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["overall_flow_score"], 1.0)

    def test_identical_keywords_score_one(self):
        scenes = [
            {"scene": 1, "search_query": "morning water glass"},
            {"scene": 2, "search_query": "morning water glass"},
        ]
        result = analyze_flow(scenes)
        self.assertEqual(result["pairs"][0]["continuity_score"], 1.0)

    def test_completely_different_keywords_score_zero(self):
        scenes = [
            {"scene": 1, "search_query": "morning water glass"},
            {"scene": 2, "search_query": "night city lights"},
        ]
        result = analyze_flow(scenes)
        self.assertEqual(result["pairs"][0]["continuity_score"], 0.0)

    def test_partial_overlap_between_zero_and_one(self):
        result = analyze_flow(SCENES)
        score = result["pairs"][0]["continuity_score"]
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_pairs_reference_correct_scene_numbers(self):
        result = analyze_flow(SCENES)
        self.assertEqual(
            [(p["from_scene"], p["to_scene"]) for p in result["pairs"]],
            [(1, 2), (2, 3)],
        )

    def test_missing_search_query_falls_back_to_image_prompt(self):
        scenes = [
            {"scene": 1, "image_prompt": "Ultra realistic morning water glass on table."},
            {"scene": 2, "image_prompt": "Ultra realistic morning water digestion habit."},
        ]
        result = analyze_flow(scenes)
        self.assertGreater(result["pairs"][0]["continuity_score"], 0.0)

    def test_scenes_out_of_order_are_sorted_before_analysis(self):
        shuffled = [SCENES[2], SCENES[0], SCENES[1]]
        result = analyze_flow(shuffled)
        self.assertEqual(
            [(p["from_scene"], p["to_scene"]) for p in result["pairs"]],
            [(1, 2), (2, 3)],
        )


class TestAnnotateScenesWithFlow(unittest.TestCase):

    def test_first_scene_has_none_continuity(self):
        result = annotate_scenes_with_flow(SCENES)
        self.assertIsNone(result[0]["flow_continuity"])

    def test_later_scenes_have_numeric_continuity(self):
        result = annotate_scenes_with_flow(SCENES)
        self.assertIsInstance(result[1]["flow_continuity"], float)
        self.assertIsInstance(result[2]["flow_continuity"], float)

    def test_scenes_never_reordered(self):
        shuffled = [SCENES[2], SCENES[0], SCENES[1]]
        result = annotate_scenes_with_flow(shuffled)
        self.assertEqual([s["scene"] for s in result], [1, 2, 3])

    def test_original_scenes_not_mutated(self):
        scenes_copy = [dict(s) for s in SCENES]
        annotate_scenes_with_flow(scenes_copy)
        self.assertEqual(scenes_copy, SCENES)
        self.assertNotIn("flow_continuity", scenes_copy[0])

    def test_other_fields_preserved(self):
        scenes = [
            {"scene": 1, "search_query": "a", "narration": "n1"},
            {"scene": 2, "search_query": "b", "narration": "n2"},
        ]
        result = annotate_scenes_with_flow(scenes)
        self.assertEqual(result[0]["narration"], "n1")
        self.assertEqual(result[1]["narration"], "n2")


if __name__ == "__main__":
    unittest.main()
