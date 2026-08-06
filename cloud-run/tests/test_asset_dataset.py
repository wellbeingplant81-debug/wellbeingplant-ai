"""
Sprint78 - Observatory를 데이터셋으로, 그리고 Replay.

Sprint77의 Observatory가 프로젝트마다 asset_observatory.json을 남긴다.
그것 하나로는 "이번 영상에서 무슨 일이 있었나"만 보인다. 여러 편을
가로질러 "어떤 실패가 반복되는가"를 보려면 한 표로 합쳐야 한다.

Replay는 그 위에 선다. 기록된 후보 풀이 그대로 있으므로, 새 순위
규칙을 실제 API 없이 되돌려 볼 수 있다 - "그 규칙이었다면 무엇을
골랐을까". Ranking v3를 구현하기 전에 이것부터 만드는 이유는,
Best-of-N에서 표본 없이 착수했다가 기각당한 전례가 있기 때문이다.
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


def _observatory(scenes):
    return {
        "schema_version": "sprint77",
        "cache": {"hits": 0, "misses": len(scenes)},
        "scenes": scenes,
    }


def _scene_record(number, candidates, selected_index, searches=1):
    recorded = []
    for index, (alt, relevance, score) in enumerate(candidates):
        recorded.append({
            "provider": "pexels_image",
            "alt": alt,
            "slug": "",
            "source_url": f"https://www.pexels.com/photo/x-{number}{index}/",
            "download_url": f"https://img/{number}{index}.jpg",
            "width": 1080,
            "height": 1920,
            "duration": None,
            "relevance": relevance,
            "human_penalty": 0.0,
            "composition": 0.15,
            "motion": 0.0,
            "ranking_score": score,
            "selected": index == selected_index,
        })
    return {
        "scene": number,
        "searches": [
            {"query": f"q{number}", "provider": "pexels_image",
             "cache_hit": False, "result_count": len(candidates)}
            for _ in range(searches)
        ],
        "candidates": recorded,
        "scene_terms": ["bowl", "oatmeal"],
        "selection_reason": "테스트",
        "final_provider": "pexels_image",
        "final_asset": f"/p/images/scene{number}.png",
    }


def _report(scene_results, scores=None):
    return {
        "ai_quality_evaluation": {
            "scores": scores or {
                "overall_quality": 75, "image_realism": 85,
                "composition": 90, "character_consistency": 95,
                "hook_strength": 80, "scene1_quality": 80,
                "thumbnail_quality": 80,
            },
            "scenes": [
                {"scene": number, "realism_score": realism,
                 "composition_score": 80, "regenerate": regenerate,
                 "reason": reason}
                for number, realism, regenerate, reason in scene_results
            ],
        }
    }


class _Project:
    """디스크에 관측 산출물이 있는 프로젝트 하나를 만든다."""

    def __init__(self, root, name, observatory, report):
        self.path = os.path.join(root, name)
        os.makedirs(self.path)
        with open(os.path.join(self.path, "asset_observatory.json"),
                  "w", encoding="utf-8") as f:
            json.dump(observatory, f, ensure_ascii=False)
        with open(os.path.join(self.path, "quality_report.json"),
                  "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False)


class TestDatasetBuilding(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

        _Project(
            self.root, "proj_a",
            _observatory([
                _scene_record(2, [
                    ("water pouring into a clear glass", 0.21, 1.33),
                    ("soda water with red straw", 0.29, 1.41),
                ], selected_index=1),
            ]),
            _report([(2, 30, True, "잔 안에 이상한 붉은 물체가 있습니다")]),
        )
        _Project(
            self.root, "proj_b",
            _observatory([
                _scene_record(5, [
                    ("top view of a breakfast bowl", 0.10, 1.21),
                    ("yogurt bowl held in a hand", 0.29, 1.41),
                ], selected_index=1),
            ]),
            _report([(5, 60, True, "요청된 flat lay 구도가 아닙니다")]),
        )

    def test_one_row_per_stock_scene(self):
        rows = asset_dataset.build(self.root)

        self.assertEqual(len(rows), 2)

    def test_a_row_carries_the_fields_needed_for_analysis(self):
        row = asset_dataset.build(self.root)[0]

        for field in (
            "project", "scene", "provider", "query", "candidate_count",
            "selected_rank", "selected_alt", "selected_score",
            "gemini_reason", "regenerate", "realism",
            "overall_quality", "image_realism", "composition",
            "character_consistency",
        ):
            with self.subTest(field=field):
                self.assertIn(field, row)

    def test_the_selected_rank_is_in_provider_order(self):
        """provider가 준 순서에서 몇 번째를 골랐나.

        점수 순위로 재면 항상 0이다 - 선택이 곧 최고점이기 때문이다.
        알고 싶은 것은 "Pexels의 1번을 뒤집었는가"이고, 그건 provider
        순서로만 보인다.
        """

        rows = {r["scene"]: r for r in asset_dataset.build(self.root)}

        # 두 프로젝트 다 provider 순서상 두 번째(index 1)를 골랐다.
        self.assertEqual(rows[2]["selected_rank"], 1)

    def test_the_gemini_evaluation_is_joined(self):
        rows = {r["scene"]: r for r in asset_dataset.build(self.root)}

        self.assertTrue(rows[2]["regenerate"])
        self.assertIn("붉은 물체", rows[2]["gemini_reason"])
        self.assertEqual(rows[2]["realism"], 30)

    def test_a_project_without_an_observatory_is_skipped(self):
        os.makedirs(os.path.join(self.root, "no_obs"))

        self.assertEqual(len(asset_dataset.build(self.root)), 2)

    def test_a_project_without_an_evaluation_still_yields_a_row(self):
        """평가가 아직 없어도 후보 풀은 분석 가치가 있다."""

        path = os.path.join(self.root, "no_eval")
        os.makedirs(path)
        with open(os.path.join(path, "asset_observatory.json"),
                  "w", encoding="utf-8") as f:
            json.dump(_observatory([_scene_record(1, [("x", 0.1, 1.0)], 0)]), f)

        rows = asset_dataset.build(self.root)

        self.assertEqual(len(rows), 3)
        orphan = [r for r in rows if r["project"] == "no_eval"][0]
        self.assertIsNone(orphan["gemini_reason"])


class TestStatistics(unittest.TestCase):

    def _rows(self):
        return [
            {"regenerate": True, "gemini_reason": "요청된 top-down 구도가 아닌 정면입니다",
             "selected_alt": "a bowl", "selected_rank": 0,
             "candidate_count": 5, "selected_asset": "a"},
            {"regenerate": True, "gemini_reason": "잔 안에 붉은 빨대가 보입니다",
             "selected_alt": "soda with red straw", "selected_rank": 0,
             "candidate_count": 5, "selected_asset": "b"},
            {"regenerate": True, "gemini_reason": "프롬프트의 연어가 아니라 스테이크입니다",
             "selected_alt": "steak", "selected_rank": 0,
             "candidate_count": 5, "selected_asset": "c"},
            {"regenerate": False, "gemini_reason": None,
             "selected_alt": "ok", "selected_rank": 0,
             "candidate_count": 5, "selected_asset": "d"},
            {"regenerate": True, "gemini_reason": "조명 톤이 다른 장면과 이질적입니다",
             "selected_alt": "dark", "selected_rank": 0,
             "candidate_count": 5, "selected_asset": "a"},
        ]

    def test_the_failure_rate_is_reported(self):
        stats = asset_dataset.summarize(self._rows())

        self.assertEqual(stats["rows"], 5)
        self.assertEqual(stats["failures"], 4)

    def test_failure_causes_are_counted(self):
        stats = asset_dataset.summarize(self._rows())
        causes = dict(stats["causes"])

        self.assertEqual(causes.get("구도/앵글"), 1)
        self.assertEqual(causes.get("피사체 불일치"), 1)
        self.assertEqual(causes.get("색/불필요한 요소"), 1)
        self.assertEqual(causes.get("톤/조명"), 1)

    def test_duplicate_assets_across_scenes_are_detected(self):
        stats = asset_dataset.summarize(self._rows())

        # "a"가 두 scene에서 쓰였다.
        self.assertEqual(stats["duplicates"], 1)

    def test_first_result_share_is_reported(self):
        """선택이 1번 그대로인 비율. 순위가 일하고 있는지의 지표다."""

        stats = asset_dataset.summarize(self._rows())

        self.assertEqual(stats["picked_first"], 5)

    def test_an_empty_dataset_does_not_raise(self):
        stats = asset_dataset.summarize([])

        self.assertEqual(stats["rows"], 0)
        self.assertEqual(stats["failures"], 0)


class TestReplay(unittest.TestCase):
    """기록된 후보 풀에 새 규칙을 되돌려 본다. API 호출 없음."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

        _Project(
            self.root, "proj_a",
            _observatory([
                _scene_record(2, [
                    ("water pouring into a clear glass", 0.21, 1.33),
                    ("soda water with red straw", 0.29, 1.41),
                ], selected_index=1),
            ]),
            _report([(2, 30, True, "붉은 물체")]),
        )

    def test_the_same_rule_reproduces_the_original_pick(self):
        """기록된 ranking_score를 그대로 쓰면 원래 선택이 나와야 한다.
        아니면 기록이나 재생 중 하나가 틀린 것이다."""

        result = asset_replay.replay(
            self.root, lambda candidate, scene: candidate["ranking_score"],
        )

        self.assertEqual(result["changed"], 0)
        self.assertEqual(result["scenes"], 1)

    def test_a_new_rule_that_changes_the_pick_is_reported(self):
        def penalise_straw(candidate, scene):
            score = candidate["ranking_score"]
            if "straw" in (candidate["alt"] or "").lower():
                score -= 0.5
            return score

        result = asset_replay.replay(self.root, penalise_straw)

        self.assertEqual(result["changed"], 1)
        self.assertEqual(result["changed_on_failed"], 1)
        self.assertEqual(result["changed_on_passed"], 0)

    def test_each_change_is_explained(self):
        def penalise_straw(candidate, scene):
            score = candidate["ranking_score"]
            if "straw" in (candidate["alt"] or "").lower():
                score -= 0.5
            return score

        change = asset_replay.replay(self.root, penalise_straw)["changes"][0]

        self.assertEqual(change["scene"], 2)
        self.assertIn("straw", change["was"])
        self.assertIn("clear glass", change["now"])
        self.assertTrue(change["was_failure"])

    def test_replay_never_calls_an_api(self):
        """규칙이 후보 dict와 scene dict만 받는다는 계약.

        네트워크를 막을 방법은 없지만, 재생이 디스크의 기록만 읽고
        원본 provider 응답을 다시 만들지 않는다는 것은 고정할 수 있다.
        """

        seen = []

        def spy(candidate, scene):
            seen.append(set(candidate))
            return candidate["ranking_score"]

        asset_replay.replay(self.root, spy)

        for keys in seen:
            self.assertIn("alt", keys)
            self.assertIn("ranking_score", keys)

    def test_replay_does_not_mutate_the_recorded_data(self):
        def mutating(candidate, scene):
            candidate["alt"] = "CHANGED"
            return 1.0

        asset_replay.replay(self.root, mutating)

        with open(
            os.path.join(self.root, "proj_a", "asset_observatory.json"),
            encoding="utf-8",
        ) as f:
            payload = json.load(f)

        alts = [c["alt"] for c in payload["scenes"][0]["candidates"]]
        self.assertNotIn("CHANGED", alts)

    def test_an_empty_root_replays_nothing(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(lambda: os.rmdir(empty))

        result = asset_replay.replay(empty, lambda c, s: 0.0)

        self.assertEqual(result["scenes"], 0)
        self.assertEqual(result["changed"], 0)


class TestClassifierHandlesBothLanguages(unittest.TestCase):
    """Gemini는 한국어로도 영어로도 답한다.

    실측 - 같은 파이프라인에서 둘 다 나왔다. 영어 사유가 조용히
    "기타"로 새면 통계가 그만큼 쓸모없어진다.
    """

    def test_an_english_composition_failure_is_classified(self):
        self.assertEqual(
            asset_dataset.classify(
                "The image does not follow the 'flat lay' composition requested"
            ),
            "구도/앵글",
        )

    def test_an_english_distractor_failure_is_classified(self):
        self.assertEqual(
            asset_dataset.classify(
                "The image shows a strange red object in the glass"
            ),
            "색/불필요한 요소",
        )

    def test_the_korean_equivalents_still_classify(self):
        self.assertEqual(
            asset_dataset.classify("요청된 top-down 구도가 아닌 정면입니다"),
            "구도/앵글",
        )

    def test_an_empty_reason_is_not_an_error(self):
        self.assertEqual(asset_dataset.classify(None), "사유 없음")


if __name__ == "__main__":
    unittest.main()
