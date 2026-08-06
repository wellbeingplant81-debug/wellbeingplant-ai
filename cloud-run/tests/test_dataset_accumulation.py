"""
Sprint79 - Production 운용으로 축적한다.

Sprint78까지 Dataset Builder와 Replay Harness는 만들었지만, 쓰려면
매번 손으로 돌려야 했고 산출물이 흩어진 프로젝트 디렉터리에만 있었다.
여기서는 영상을 만들 때마다 한 곳에 쌓인다.

두 가지가 특히 중요하다.

  1. 같은 프로젝트를 두 번 쌓지 않는다. 파이프라인이 재실행되거나
     수동으로 다시 부를 수 있고, 중복이 쌓이면 실패율 통계가 조용히
     왜곡된다.

  2. 축적된 데이터만으로 Replay가 돌아야 한다. 후보 풀을 행에 담지
     않으면 원본 프로젝트 디렉터리가 사라진 뒤 재생할 수 없다.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.tools import asset_dataset, asset_replay


def _observatory(scene_number, candidates, selected_index):
    recorded = []
    for index, (alt, score) in enumerate(candidates):
        recorded.append({
            "provider": "pexels_image",
            "alt": alt,
            "slug": "",
            "source_url": f"https://p/{scene_number}{index}/",
            "download_url": f"https://img/{scene_number}{index}.jpg",
            "width": 1080, "height": 1920, "duration": None,
            "relevance": 0.2, "human_penalty": 0.0,
            "composition": 0.15, "motion": 0.0,
            "ranking_score": score,
            "selected": index == selected_index,
        })
    return {
        "schema_version": "sprint77",
        "cache": {"hits": 1, "misses": 2},
        "scenes": [{
            "scene": scene_number,
            "searches": [
                {"query": "q", "provider": "pexels_image",
                 "cache_hit": False, "result_count": len(candidates)},
                {"query": "q", "provider": "pexels_video",
                 "cache_hit": True, "result_count": 0},
            ],
            "candidates": recorded,
            "scene_terms": ["bowl", "oatmeal"],
            "selection_reason": "테스트",
            "final_provider": "pexels_image",
            "final_asset": f"/p/images/scene{scene_number}.png",
        }],
    }


def _report(scene_number, regenerate, reason):
    return {
        "ai_quality_evaluation": {
            "scores": {
                "overall_quality": 75, "image_realism": 85,
                "composition": 90, "character_consistency": 95,
                "hook_strength": 80, "scene1_quality": 80,
                "thumbnail_quality": 80,
            },
            "scenes": [{
                "scene": scene_number, "realism_score": 40,
                "composition_score": 80,
                "regenerate": regenerate, "reason": reason,
            }],
        }
    }


def _make_project(root, name, scene_number=2, selected_index=1,
                  regenerate=True, reason="붉은 빨대가 보입니다"):
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)

    with open(os.path.join(path, "asset_observatory.json"),
              "w", encoding="utf-8") as f:
        json.dump(_observatory(scene_number, [
            ("water pouring into a clear glass", 1.33),
            ("soda water with red straw", 1.41),
        ], selected_index), f, ensure_ascii=False)

    with open(os.path.join(path, "quality_report.json"),
              "w", encoding="utf-8") as f:
        json.dump(_report(scene_number, regenerate, reason), f,
                  ensure_ascii=False)

    return path


class TestAccumulation(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.dataset = os.path.join(self.root, "dataset.jsonl")

    def test_appending_a_project_writes_its_rows(self):
        project = _make_project(self.root, "proj_a")

        added = asset_dataset.append_project(project, self.dataset)

        self.assertEqual(added, 1)
        self.assertEqual(len(asset_dataset.load(self.dataset)), 1)

    def test_appending_the_same_project_twice_adds_nothing(self):
        """파이프라인이 재실행되거나 수동으로 다시 불릴 수 있다.
        중복이 쌓이면 실패율 통계가 조용히 왜곡된다."""

        project = _make_project(self.root, "proj_a")

        asset_dataset.append_project(project, self.dataset)
        added = asset_dataset.append_project(project, self.dataset)

        self.assertEqual(added, 0)
        self.assertEqual(len(asset_dataset.load(self.dataset)), 1)

    def test_different_projects_accumulate(self):
        asset_dataset.append_project(
            _make_project(self.root, "proj_a"), self.dataset,
        )
        asset_dataset.append_project(
            _make_project(self.root, "proj_b", scene_number=5), self.dataset,
        )

        rows = asset_dataset.load(self.dataset)

        self.assertEqual(len(rows), 2)
        self.assertEqual({r["project"] for r in rows}, {"proj_a", "proj_b"})

    def test_a_project_with_no_stock_scenes_adds_nothing(self):
        path = os.path.join(self.root, "all_ai")
        os.makedirs(path)
        with open(os.path.join(path, "asset_observatory.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"schema_version": "sprint77",
                       "cache": {"hits": 0, "misses": 0},
                       "scenes": [{"scene": 1, "searches": [],
                                   "candidates": [], "scene_terms": [],
                                   "selection_reason": "Imagen",
                                   "final_provider": "ai_image",
                                   "final_asset": "/p/scene1.png"}]}, f)

        added = asset_dataset.append_project(path, self.dataset)

        self.assertEqual(added, 0)

    def test_appending_never_raises_on_a_missing_project(self):
        """관측이 생산을 막지 않는다 - Sprint73에서 세운 원칙."""

        added = asset_dataset.append_project(
            os.path.join(self.root, "nope"), self.dataset,
        )

        self.assertEqual(added, 0)

    def test_a_corrupt_dataset_line_is_skipped_not_fatal(self):
        project = _make_project(self.root, "proj_a")
        asset_dataset.append_project(project, self.dataset)

        with open(self.dataset, "a", encoding="utf-8") as f:
            f.write("{ this is not json\n")

        self.assertEqual(len(asset_dataset.load(self.dataset)), 1)

    def test_the_cache_counters_survive_into_the_row(self):
        asset_dataset.append_project(
            _make_project(self.root, "proj_a"), self.dataset,
        )

        row = asset_dataset.load(self.dataset)[0]

        self.assertEqual(row["search_count"], 2)
        self.assertEqual(row["cache_hits"], 1)


class TestDatasetIsSelfSufficientForReplay(unittest.TestCase):
    """축적된 행만으로 재생이 돌아야 한다.

    후보 풀을 행에 담지 않으면 원본 프로젝트 디렉터리가 지워진 뒤
    재생할 수 없다. scratchpad는 임시 디렉터리다.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.dataset = os.path.join(self.root, "dataset.jsonl")
        asset_dataset.append_project(
            _make_project(self.root, "proj_a"), self.dataset,
        )

    def test_a_row_carries_the_whole_candidate_pool(self):
        row = asset_dataset.load(self.dataset)[0]

        self.assertEqual(len(row["candidates"]), 2)
        self.assertIn("alt", row["candidates"][0])
        self.assertIn("ranking_score", row["candidates"][0])

    def test_replay_runs_from_rows_alone(self):
        rows = asset_dataset.load(self.dataset)

        result = asset_replay.replay_rows(
            rows, lambda c, s: c["ranking_score"],
        )

        self.assertEqual(result["scenes"], 1)
        self.assertEqual(result["changed"], 0)

    def test_a_new_rule_replays_from_rows_alone(self):
        rows = asset_dataset.load(self.dataset)

        def penalise_straw(candidate, scene):
            score = candidate["ranking_score"]
            if "straw" in (candidate["alt"] or "").lower():
                score -= 0.5
            return score

        result = asset_replay.replay_rows(rows, penalise_straw)

        self.assertEqual(result["changed"], 1)
        self.assertEqual(result["changed_on_failed"], 1)

    def test_replay_works_after_the_project_directory_is_gone(self):
        import shutil
        shutil.rmtree(os.path.join(self.root, "proj_a"))

        rows = asset_dataset.load(self.dataset)
        result = asset_replay.replay_rows(
            rows, lambda c, s: c["ranking_score"],
        )

        self.assertEqual(result["scenes"], 1)


class TestReadinessGate(unittest.TestCase):
    """Ranking v3 착수 조건을 코드가 판정한다.

    사람이 눈대중으로 "이 정도면 됐다"고 판단하면 Best-of-N을 다시
    한다. 조건은 사용자가 정했다 - 실패 스톡 scene 30개 또는 전체
    100 scene.
    """

    def _rows(self, total, failures):
        return [
            {"regenerate": index < failures, "gemini_reason": "x",
             "selected_asset": f"a{index}", "selected_rank": 0,
             "candidate_count": 5}
            for index in range(total)
        ]

    def test_not_ready_below_both_thresholds(self):
        gate = asset_dataset.readiness(self._rows(10, 5))

        self.assertFalse(gate["ready"])

    def test_ready_at_thirty_failures(self):
        gate = asset_dataset.readiness(self._rows(40, 30))

        self.assertTrue(gate["ready"])
        self.assertIn("실패", gate["reason"])

    def test_ready_at_one_hundred_scenes(self):
        gate = asset_dataset.readiness(self._rows(100, 3))

        self.assertTrue(gate["ready"])

    def test_the_gate_reports_how_far_away_it_is(self):
        gate = asset_dataset.readiness(self._rows(10, 4))

        self.assertEqual(gate["failures"], 4)
        self.assertEqual(gate["scenes"], 10)
        self.assertEqual(gate["failures_needed"], 26)
        self.assertEqual(gate["scenes_needed"], 90)


if __name__ == "__main__":
    unittest.main()
