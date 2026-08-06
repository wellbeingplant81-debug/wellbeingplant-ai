"""
Sprint82 - Replay Viewer.

순수 뷰어다. 이 테스트들이 지키는 것은 두 가지다.

  1. 아무것도 바꾸지 않는다. 데이터셋도, Observatory도, 생산 산출물도.
  2. 지어내지 않는다. 데이터가 없으면 없다고 말한다 - 뷰어가 빈 화면
     대신 그럴듯한 숫자를 보여 주면 그것이 판단 근거가 되어 버린다.

그리고 replay_rules가 Production 순위로 새어 들어가지 않는지도 본다.
그 규칙들은 아직 채택되지 않은 가설이고, Ranking v3 게이트가 열리기
전에는 실제 선택에 영향을 주면 안 된다.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import studio_replay
from app.tools import asset_dataset, replay_rules


def _candidate(alt, score, selected=False, **overrides):
    candidate = {
        "provider": "pexels_image", "alt": alt, "slug": "",
        "source_url": f"https://p/{abs(hash(alt)) % 999}/",
        "download_url": "https://i/x.jpg",
        "width": 1080, "height": 1920, "duration": None,
        "relevance": 0.2, "human_penalty": 0.0,
        "composition": 0.15, "motion": 0.0,
        "ranking_score": score, "selected": selected,
    }
    candidate.update(overrides)
    return candidate


def _row(scene=2, candidates=None, regenerate=True, terms=None):
    return {
        "project": "p1", "scene": scene, "provider": "pexels_image",
        "query": "q", "search_count": 1, "cache_hits": 0,
        "candidate_count": len(candidates or []),
        "selected_rank": 0, "selected_alt": None, "selected_slug": None,
        "selected_score": None, "selected_relevance": None,
        "selected_asset": None, "best_alternative_alt": None,
        "gemini_reason": "붉은 물체" if regenerate else None,
        "regenerate": regenerate, "realism": 30,
        "overall_quality": 70, "image_realism": 80,
        "composition": 75, "character_consistency": 90,
        "has_evaluation": True,
        "candidates": candidates or [],
        "scene_terms": terms or ["glass", "water"],
    }


class TestRuleCatalog(unittest.TestCase):

    def test_the_four_rules_the_epic_asked_for_exist(self):
        keys = {rule["key"] for rule in replay_rules.catalog()}

        self.assertEqual(
            keys,
            {replay_rules.BASELINE, replay_rules.NEGATIVE,
             replay_rules.COMPOSITION, replay_rules.COMBINED},
        )

    def test_every_rule_has_a_label_and_description(self):
        for rule in replay_rules.catalog():
            with self.subTest(rule=rule["key"]):
                self.assertTrue(rule["label"])
                self.assertTrue(rule["description"])

    def test_the_catalog_does_not_leak_callables(self):
        for rule in replay_rules.catalog():
            self.assertNotIn("scorer", rule)

    def test_an_unknown_rule_is_rejected(self):
        with self.assertRaises(ValueError):
            replay_rules.scorer_for("wishful_thinking")


class TestRulesAreNotProduction(unittest.TestCase):
    """이 Epic의 핵심 계약 - 아직 채택되지 않은 가설이다."""

    def _imports(self, module):
        import ast

        source = open(module.__file__, encoding="utf-8").read()
        tree = ast.parse(source)

        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(f"{node.module}.{alias.name}")
        return names

    def test_the_relevance_scorer_never_imports_replay_rules(self):
        from app.services import asset_relevance

        for name in self._imports(asset_relevance):
            self.assertNotIn("replay_rules", name)

    def test_the_ranking_service_never_imports_replay_rules(self):
        from app.services import asset_ranking_service

        for name in self._imports(asset_ranking_service):
            self.assertNotIn("replay_rules", name)

    def test_asset_integration_never_imports_replay_rules(self):
        from app.services import asset_integration_service

        for name in self._imports(asset_integration_service):
            self.assertNotIn("replay_rules", name)


class TestBaselineReproduces(unittest.TestCase):
    """기준선이 원본을 재현하지 못하면 나머지 재생 결과를 믿을 수 없다."""

    def test_baseline_changes_nothing(self):
        rows = [_row(candidates=[
            _candidate("water in a clear glass", 1.33),
            _candidate("soda water with red straw", 1.41, selected=True),
        ])]

        with patch.object(asset_dataset, "load", return_value=rows):
            view = studio_replay.replay_view(replay_rules.BASELINE)

        self.assertEqual(view["changed"], 0)
        self.assertEqual(view["rows"][0]["status"], "UNCHANGED")


class TestWouldChange(unittest.TestCase):

    def _rows(self):
        return [_row(candidates=[
            _candidate("water pouring into a clear glass", 1.33),
            _candidate("soda water with bubbles and red straw", 1.41,
                       selected=True),
        ])]

    def test_a_rule_that_moves_the_winner_is_marked(self):
        with patch.object(asset_dataset, "load", return_value=self._rows()):
            view = studio_replay.replay_view(replay_rules.NEGATIVE)

        row = view["rows"][0]

        self.assertEqual(row["status"], "WOULD CHANGE")
        self.assertIn("straw", row["original_winner"])
        self.assertIn("clear glass", row["new_winner"])
        self.assertTrue(row["reason"])

    def test_changes_are_split_by_whether_the_scene_had_failed(self):
        rows = self._rows() + [_row(
            scene=4, regenerate=False,
            candidates=[
                _candidate("a plain bowl", 1.10, selected=True),
                _candidate("a bowl of oatmeal", 1.05),
            ],
        )]

        with patch.object(asset_dataset, "load", return_value=rows):
            view = studio_replay.replay_view(replay_rules.NEGATIVE)

        self.assertEqual(view["changed_on_failed"], 1)
        self.assertEqual(view["changed_on_passed"], 0)

    def test_every_candidate_carries_both_rankings(self):
        with patch.object(asset_dataset, "load", return_value=self._rows()):
            view = studio_replay.replay_view(replay_rules.NEGATIVE)

        for candidate in view["rows"][0]["candidates"]:
            for field in ("original_rank", "replay_rank", "original_score",
                          "replay_score", "delta", "relevance",
                          "human_penalty", "composition", "motion"):
                with self.subTest(field=field):
                    self.assertIn(field, candidate)


class TestMissingDataIsStated(unittest.TestCase):
    """지어내지 않는다."""

    def test_an_empty_dataset_says_so(self):
        with patch.object(asset_dataset, "load", return_value=[]):
            view = studio_replay.replay_view(replay_rules.BASELINE)

        self.assertFalse(view["has_data"])
        self.assertTrue(view["missing_reason"])
        self.assertEqual(view["rows"], [])
        self.assertEqual(view["scenes"], 0)

    def test_rows_without_candidates_are_not_counted_as_data(self):
        with patch.object(
            asset_dataset, "load", return_value=[_row(candidates=[])],
        ):
            view = studio_replay.replay_view(replay_rules.BASELINE)

        self.assertFalse(view["has_data"])

    def test_a_project_without_an_observatory_says_so(self):
        with tempfile.TemporaryDirectory() as root:
            view = studio_replay.project_replay_view(root)

        self.assertFalse(view["has_data"])
        self.assertIn("후보 기록이 없습니다", view["missing_reason"])


class TestGateIsShown(unittest.TestCase):

    def test_the_ranking_v3_gate_is_reported(self):
        with patch.object(asset_dataset, "load", return_value=[]):
            gate = studio_replay.replay_view(replay_rules.BASELINE)["gate"]

        for field in ("ready", "reason", "failures", "scenes",
                      "failures_needed", "scenes_needed"):
            with self.subTest(field=field):
                self.assertIn(field, gate)


class TestNothingIsMutated(unittest.TestCase):
    """뷰어는 아무것도 바꾸지 않는다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dataset = os.path.join(self._tmp.name, "asset_dataset.jsonl")

        with open(self.dataset, "w", encoding="utf-8") as f:
            f.write(json.dumps(_row(candidates=[
                _candidate("water in a clear glass", 1.33),
                _candidate("soda water with red straw", 1.41, selected=True),
            ]), ensure_ascii=False) + "\n")

    def _digest(self):
        with open(self.dataset, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def test_the_dataset_file_is_untouched(self):
        before = self._digest()

        with patch.object(studio_replay, "_dataset_path",
                          return_value=self.dataset):
            for key in (replay_rules.BASELINE, replay_rules.NEGATIVE,
                        replay_rules.COMPOSITION, replay_rules.COMBINED):
                studio_replay.replay_view(key)

        self.assertEqual(self._digest(), before)

    def test_the_rows_handed_to_a_rule_are_copies(self):
        """규칙이 실수로 후보를 건드려도 기록이 망가지지 않아야 한다."""

        rows = [_row(candidates=[
            _candidate("a", 1.0, selected=True), _candidate("b", 0.9),
        ])]
        original = json.dumps(rows, sort_keys=True)

        def mutating(candidate, scene):
            candidate["alt"] = "CHANGED"
            candidate["ranking_score"] = 99
            return 1.0

        with patch.object(asset_dataset, "load", return_value=rows), \
                patch.object(replay_rules, "scorer_for",
                             return_value=mutating):
            studio_replay.replay_view(replay_rules.BASELINE)

        self.assertEqual(json.dumps(rows, sort_keys=True), original)


if __name__ == "__main__":
    unittest.main()
