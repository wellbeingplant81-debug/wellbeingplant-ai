"""
Sprint229 - 쌓인 기록이 hold를 센다 (Epic 68, Phase 3).

Sprint227이 프로젝트마다 "고른 영상이 이 scene을 어떻게 채웠는가"를
남기기 시작했고, Sprint228이 그 hold를 낮췄다. 그런데 그 숫자를 보려면
프로젝트를 하나씩 열어야 했다.

축적을 읽는 자리는 이미 있다 - asset_dataset.build()가 프로젝트마다
asset_observatory.json을 읽어 행으로 펴고 summarize()가 집계한다.
그 둘이 footage를 몰랐을 뿐이다.

이 회차는 관측 회차다
---------------------
생성 결과 · 순위 · Provider 선택에 아무 영향이 없다. 이미 쌓인 것을
읽어 세는 일만 한다.

분모가 이 집계의 전부다
-----------------------
영상 10개 중 hold 2개면 20%여야 한다. 그림 90개가 함께 세어지면 2%로
보이고, 그러면 아무도 이 숫자를 보고 아무 판단도 하지 않는다.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tools import asset_dataset


def _candidate(selected=True):
    return {
        "source": "pexels_video",
        "alt": "knee stretching",
        "slug": "knee-stretching",
        "source_url": "u",
        "download_url": "d",
        "width": 1080,
        "height": 1920,
        "duration": 12,
        "relevance": 1.0,
        "human_penalty": 0.0,
        "composition": 0.15,
        "motion": 0.10,
        "ranking_score": 1.25,
        "selected": selected,
    }


def _scene(number, footage=None):
    """관측 파일 안의 scene 한 덩이."""

    entry = {
        "scene": number,
        "searches": [{"query": "knee", "provider": "pexels_video",
                      "cache_hit": False, "result_count": 3}],
        "candidates": [_candidate()],
        "scene_terms": ["knee"],
        "planned": {},
        "selection_reason": "골랐다",
        "final_provider": "pexels_video",
        "final_asset": "images/scene%d.png" % number,
        "footage": footage,
    }

    return entry


def _footage(mode, source_seconds=12.0, scene_seconds=5.0):
    return {"mode": mode, "source_seconds": source_seconds,
            "scene_seconds": scene_seconds}


class _Root(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sprint229_")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def place(self, name, scenes):
        where = os.path.join(self.root, name)
        os.makedirs(where, exist_ok=True)

        with open(os.path.join(where, "asset_observatory.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"schema_version": "sprint83", "scenes": scenes}, f,
                      ensure_ascii=False)

        return where


class TheRowCarriesHowItWasFilledTest(_Root):
    """행에 실려야 세는 쪽이 볼 수 있다."""

    def test_the_three_fields_are_on_the_row(self):
        self.place("proj_a", [_scene(1, _footage("trim", 12.0, 5.25))])

        row = asset_dataset.build(self.root)[0]

        self.assertEqual(row["footage_mode"], "trim")
        self.assertEqual(row["source_seconds"], 12.0)
        self.assertEqual(row["scene_seconds"], 5.25)

    def test_a_scene_that_used_a_picture_says_nothing(self):
        """영상이 아니었던 scene은 셋 다 None이다."""

        self.place("proj_a", [_scene(1, None)])

        row = asset_dataset.build(self.root)[0]

        self.assertIsNone(row["footage_mode"])
        self.assertIsNone(row["source_seconds"])
        self.assertIsNone(row["scene_seconds"])

    def test_an_older_project_is_read_as_before(self):
        """
        Sprint227 이전에 쌓인 관측 파일에는 footage 칸이 아예 없다.
        없다고 행을 버리지 않는다 - 버리면 지금까지 모은 것이 통째로
        죽는다(Sprint83이 planned에서 같은 판단을 했다).
        """

        entry = _scene(1)
        entry.pop("footage")

        self.place("old_proj", [entry])

        rows = asset_dataset.build(self.root)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["footage_mode"])

    def test_the_rest_of_the_row_is_unchanged(self):
        """기존 표를 깨지 않는다."""

        self.place("proj_a", [_scene(1, _footage("trim"))])

        row = asset_dataset.build(self.root)[0]

        for field in ("project", "scene", "provider", "query",
                      "search_count", "cache_hits", "candidate_count",
                      "selected_rank", "selected_alt", "selected_score",
                      "gemini_reason", "regenerate", "has_evaluation",
                      "candidates", "scene_terms", "planned", "has_plan"):
            with self.subTest(field=field):
                self.assertIn(field, row)


class ItCountsAcrossProjectsTest(_Root):
    """여러 편에 걸쳐 센다 - 한 편만 보면 알 수 없는 것이 목적이다."""

    def _summary(self):
        return asset_dataset.summarize(asset_dataset.build(self.root))

    def test_three_ways_are_counted_apart(self):
        self.place("proj_a", [
            _scene(1, _footage("trim")),
            _scene(2, _footage("loop")),
        ])
        self.place("proj_b", [
            _scene(1, _footage("hold")),
            _scene(2, _footage("trim")),
        ])

        found = self._summary()

        self.assertEqual(found["footage_scenes"], 4)
        self.assertEqual(found["footage_trim"], 2)
        self.assertEqual(found["footage_loop"], 1)
        self.assertEqual(found["footage_hold"], 1)

    def test_the_hold_rate_is_out_of_the_video_scenes_only(self):
        """
        영상 10개 중 hold 2개면 20%다. 그림은 분모에 들어가지 않는다.
        """

        video = [_scene(n, _footage("trim")) for n in range(1, 9)]
        video += [_scene(9, _footage("hold")), _scene(10, _footage("hold"))]

        pictures = [_scene(n, None) for n in range(11, 101)]

        self.place("proj_a", video + pictures)

        found = self._summary()

        self.assertEqual(found["footage_scenes"], 10)
        self.assertEqual(found["footage_hold"], 2)
        self.assertAlmostEqual(found["footage_hold_rate"], 20.0)

    def test_a_dataset_with_no_video_says_there_is_no_rate(self):
        """
        0.0으로 적으면 "영상을 썼는데 hold가 하나도 없었다"와 구별되지
        않는다. 없는 것은 없다고 한다.
        """

        self.place("proj_a", [_scene(1, None), _scene(2, None)])

        found = self._summary()

        self.assertEqual(found["footage_scenes"], 0)
        self.assertEqual(found["footage_trim"], 0)
        self.assertEqual(found["footage_loop"], 0)
        self.assertEqual(found["footage_hold"], 0)
        self.assertIsNone(found["footage_hold_rate"])

    def test_an_empty_table_does_not_divide_by_zero(self):
        found = asset_dataset.summarize([])

        self.assertEqual(found["footage_scenes"], 0)
        self.assertIsNone(found["footage_hold_rate"])

    def test_all_holds_is_a_hundred_percent(self):
        self.place("proj_a", [_scene(1, _footage("hold")),
                              _scene(2, _footage("hold"))])

        self.assertAlmostEqual(self._summary()["footage_hold_rate"], 100.0)

    def test_older_projects_mixed_in_do_not_break_it(self):
        old = _scene(1)
        old.pop("footage")

        self.place("old_proj", [old])
        self.place("new_proj", [_scene(1, _footage("hold")),
                                _scene(2, _footage("trim"))])

        found = self._summary()

        self.assertEqual(found["rows"], 3)
        self.assertEqual(found["footage_scenes"], 2)
        self.assertAlmostEqual(found["footage_hold_rate"], 50.0)

    def test_the_old_summary_is_unchanged(self):
        self.place("proj_a", [_scene(1, _footage("trim"))])

        found = self._summary()

        for field in ("rows", "projects", "failures", "failure_rate",
                      "causes", "duplicates", "picked_first",
                      "picked_lower", "with_evaluation", "mean_candidates"):
            with self.subTest(field=field):
                self.assertIn(field, found)


class TheNamesMustNotDriftTest(unittest.TestCase):
    """
    이 파일은 세 글자를 직접 적는다 - footage 모듈을 들이면 moviepy가
    딸려 오고, 이 모듈은 라우터가 최상단에서 들이는 자리다.

    그래서 갈라지지 않는 것을 여기서 잠근다. 갈라지는 날 이 집계는
    조용히 0을 세게 되므로, 조용히 지나가지 않게 하는 것이 요점이다.
    """

    def test_they_are_the_ones_the_render_writes(self):
        from app.services import footage

        self.assertEqual(asset_dataset.FOOTAGE_TRIM, footage.TRIM)
        self.assertEqual(asset_dataset.FOOTAGE_LOOP, footage.LOOP)
        self.assertEqual(asset_dataset.FOOTAGE_HOLD, footage.HOLD)

    def test_reading_the_table_does_not_drag_in_the_renderer(self):
        """
        화면을 켜는 것만으로 moviepy 가 딸려 오면 시작이 십수 초 느려
        진다 - 이 저장소가 여러 번 지켜 온 자리다.
        """

        import ast

        with open(asset_dataset.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        top_level = set()

        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level.add(node.module)

        for name in sorted(top_level):
            with self.subTest(name=name):
                self.assertNotIn("moviepy", name)
                self.assertNotIn("footage", name)


class TheReportPrintsItTest(_Root):
    """사람이 실제로 보는 자리에 나온다. 새 화면을 만들지 않는다."""

    def _said(self, summary):
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts"))

        import asset_usage_report

        caught = io.StringIO()

        with redirect_stdout(caught):
            asset_usage_report.print_footage_report(summary, "어딘가")

        return caught.getvalue()

    def test_it_prints_the_three_ways_and_the_rate(self):
        self.place("proj_a", [_scene(1, _footage("trim")),
                              _scene(2, _footage("hold"))])

        said = self._said(
            asset_dataset.summarize(asset_dataset.build(self.root)))

        self.assertIn("영상 scene 수 : 2", said)
        self.assertIn("trim", said)
        self.assertIn("loop", said)
        self.assertIn("hold", said)
        self.assertIn("50.0%", said)

    def test_it_says_so_when_there_is_nothing_yet(self):
        """
        0%로 적으면 "영상을 썼는데 hold 가 없었다"로 읽힌다.
        """

        said = self._said(asset_dataset.summarize([]))

        self.assertIn("아직 영상을 쓴 scene이 없습니다", said)
        self.assertNotIn("%", said)

    def test_it_points_at_the_file_it_read(self):
        said = self._said(asset_dataset.summarize([]))

        self.assertIn("어딘가", said)


if __name__ == "__main__":
    unittest.main()
