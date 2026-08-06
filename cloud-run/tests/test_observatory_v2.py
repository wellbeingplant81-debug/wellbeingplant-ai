"""
Sprint83 - Observatory v2. scene이 계획한 것을 함께 남긴다.

Sprint82에서 드러난 구멍을 메운다. 구도 어휘 규칙이 재생에서 한 건도
바꾸지 못했는데, 규칙이 나빠서가 아니라 **볼 것이 없어서**였다 -
scene_terms는 subject/action/environment만 담고, camera/composition은
Sprint76이 검색어에서 뺀 뒤로 아무 데도 기록되지 않았다.

기록만 늘린다. 순위는 건드리지 않고 API도 늘지 않는다 - 이미 손에
쥐고 있는 scene dict에서 읽어 적을 뿐이다.

purpose는 적을 수 없다. scene에 없는 필드이고, 만드는 곳은
scene_planner_service인데 ENABLE_SCENE_PLANNER가 False다(Sprint69/70에서
A/B 결론이 나지 않아 껐다). 추론하지 말라는 요구가 있으므로 자리만
두고 비워 둔다.
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

from app.services import asset_observatory as observatory
from app.tools import asset_dataset


def _candidate(alt="a bowl"):
    return {
        "source": "pexels_image", "alt": alt,
        "source_url": "https://p/1/", "download_url": "https://i/1.jpg",
        "width": 1080, "height": 1920,
    }


class TestPlannedFieldsAreRecorded(unittest.TestCase):

    def setUp(self):
        observatory.start()
        self.addCleanup(observatory.abandon)

    def _scene(self, **overrides):
        scene = {
            "scene": 4,
            "subject": "a ceramic bowl of oatmeal",
            "action": "on a wooden table",
            "environment": "a sunlit kitchen",
            "camera": "top-down view, camera directly above",
            "composition": "flat lay, centered",
            "lighting": "warm morning light",
            "visual_type": "real",
        }
        scene.update(overrides)
        return scene

    def test_the_scene_plan_is_recorded(self):
        observatory.record_ranking(
            4, self._scene(), [_candidate()], chosen=None, scores=[0.0],
        )

        plan = observatory.snapshot()[4]["planned"]

        self.assertEqual(plan["camera"], "top-down view, camera directly above")
        self.assertEqual(plan["composition"], "flat lay, centered")
        self.assertEqual(plan["visual_type"], "real")

    def test_purpose_is_absent_not_invented(self):
        """scene에 purpose가 없다. 만드는 곳은 scene_planner_service인데
        그 플래그는 False다. 추론하지 않는다."""

        plan = observatory.snapshot() or {}

        observatory.record_ranking(
            4, self._scene(), [_candidate()], chosen=None, scores=[0.0],
        )

        plan = observatory.snapshot()[4]["planned"]

        self.assertIn("purpose", plan)
        self.assertIsNone(plan["purpose"])

    def test_a_purpose_present_on_the_scene_is_recorded_as_is(self):
        """언젠가 scene_planner를 켜서 scene에 purpose가 실리면 그때는
        그대로 적는다. 만들어 내지는 않는다."""

        observatory.record_ranking(
            4, self._scene(purpose="evidence"), [_candidate()],
            chosen=None, scores=[0.0],
        )

        self.assertEqual(
            observatory.snapshot()[4]["planned"]["purpose"], "evidence",
        )

    def test_missing_fields_are_null_not_empty_string(self):
        """"기록되지 않음"과 "빈 값"은 다르다. 화면이 그 둘을 다르게
        보여 줘야 한다."""

        observatory.record_ranking(
            4, {"scene": 4, "subject": "a bowl"}, [_candidate()],
            chosen=None, scores=[0.0],
        )

        plan = observatory.snapshot()[4]["planned"]

        for field in ("camera", "composition", "visual_type", "purpose"):
            with self.subTest(field=field):
                self.assertIsNone(plan[field])

    def test_the_schema_version_moved(self):
        """구 데이터셋과 신 데이터셋을 구분할 수 있어야 한다."""

        self.assertNotEqual(observatory.SCHEMA_VERSION, "sprint77")

    def test_recording_still_works_without_a_scene(self):
        observatory.record_ranking(4, None, [_candidate()],
                                   chosen=None, scores=[0.0])

        self.assertIn("planned", observatory.snapshot()[4])


class TestDatasetCarriesThePlan(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _project(self, name, planned):
        path = os.path.join(self._tmp.name, name)
        os.makedirs(path)

        scene = {
            "scene": 2, "searches": [], "candidates": [{
                "provider": "pexels_image", "alt": "a bowl", "slug": "",
                "source_url": "https://p/1/", "download_url": "https://i/1.jpg",
                "width": 1080, "height": 1920, "duration": None,
                "relevance": 0.2, "human_penalty": 0.0,
                "composition": 0.15, "motion": 0.0,
                "ranking_score": 1.2, "selected": True,
            }],
            "scene_terms": ["bowl"], "selection_reason": "x",
            "final_provider": "pexels_image", "final_asset": "/p/s2.png",
        }

        if planned is not None:
            scene["planned"] = planned

        with open(os.path.join(path, "asset_observatory.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"schema_version": "sprint83",
                       "cache": {"hits": 0, "misses": 1},
                       "scenes": [scene]}, f, ensure_ascii=False)

        return path

    def test_a_new_record_carries_the_plan_into_the_row(self):
        path = self._project("new", {
            "camera": "top-down view", "composition": "flat lay",
            "visual_type": "real", "purpose": None,
        })

        row = asset_dataset.build(path)[0]

        self.assertEqual(row["planned"]["camera"], "top-down view")
        self.assertEqual(row["planned"]["composition"], "flat lay")

    def test_an_old_record_without_a_plan_still_builds(self):
        """Sprint77~82에 쌓인 것들은 planned가 없다. 읽히지 않으면
        지금까지 모은 9행이 통째로 죽는다."""

        path = self._project("old", None)

        rows = asset_dataset.build(path)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["planned"]["camera"])

    def test_an_old_row_reports_nothing_recorded(self):
        path = self._project("old", None)

        row = asset_dataset.build(path)[0]

        self.assertFalse(row["has_plan"])

    def test_a_new_row_reports_a_plan(self):
        path = self._project("new", {
            "camera": "close-up", "composition": None,
            "visual_type": "ai", "purpose": None,
        })

        self.assertTrue(asset_dataset.build(path)[0]["has_plan"])


class TestReplayViewerShowsBothVersions(unittest.TestCase):

    def _row(self, planned=None):
        return {
            "project": "p", "scene": 2, "provider": "pexels_image",
            "query": "q", "regenerate": False, "gemini_reason": None,
            "realism": 90, "scene_terms": ["bowl"],
            "candidates": [{
                "provider": "pexels_image", "alt": "a bowl", "slug": "",
                "width": 1080, "height": 1920, "duration": None,
                "relevance": 0.2, "human_penalty": 0.0,
                "composition": 0.15, "motion": 0.0,
                "ranking_score": 1.2, "selected": True,
            }],
            "planned": planned or {
                "camera": None, "composition": None,
                "visual_type": None, "purpose": None,
            },
            "has_plan": bool(planned),
        }

    def test_a_row_view_exposes_the_plan(self):
        from app.services import studio_replay
        from app.tools import replay_rules

        view = studio_replay._row_view(
            self._row({"camera": "top-down view", "composition": "flat lay",
                       "visual_type": "real", "purpose": None}),
            replay_rules.baseline,
        )

        self.assertTrue(view["has_plan"])
        self.assertEqual(view["planned"]["camera"], "top-down view")

    def test_an_old_row_view_says_nothing_was_recorded(self):
        from app.services import studio_replay
        from app.tools import replay_rules

        view = studio_replay._row_view(self._row(), replay_rules.baseline)

        self.assertFalse(view["has_plan"])
        self.assertIsNone(view["planned"]["camera"])


if __name__ == "__main__":
    unittest.main()
