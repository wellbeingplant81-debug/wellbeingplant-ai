"""
Sprint84 - Production Workflow.

상태를 저장하지 않고 산출물에서 유도한다. 사람이 내린 결정(승인)만
저장한다.

유도하는 이유가 있다. 상태를 파일에 적어 두면 그 순간의 사실이 굳어
버린다 - "Inspection"으로 적어 둔 프로젝트를 나중에 재생성해서 scene이
실패해도 파일은 여전히 Inspection이라고 말한다. script.json이 있으면
대본이 끝난 것이고 실패한 scene이 있으면 재생성이 필요한 것이다.
이 판정은 언제 물어도 지금의 사실을 답한다.

승인은 다르다. 그것은 파일에서 유도할 수 없는 사람의 판단이므로
저장해야 하고, 새로고침을 넘어 살아남아야 한다.

저장 위치는 프로젝트 디렉터리 밖이다. 생산 산출물은 손대지 않는다.
"""

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

from app.services import studio_workflow as workflow


def _project(root, name, script=True, evaluated=True, failed=()):
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)

    with open(os.path.join(path, "project.json"), "w", encoding="utf-8") as f:
        json.dump({"topic": "혈관 건강", "channel": "wellbeing"}, f,
                  ensure_ascii=False)

    if script:
        with open(os.path.join(path, "script.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"title": "제목", "scenes": [
                {"scene": n} for n in (1, 2, 3)]}, f, ensure_ascii=False)

    if evaluated:
        with open(os.path.join(path, "quality_report.json"), "w",
                  encoding="utf-8") as f:
            json.dump({
                "technical_validation": {
                    "checks": {"video_duration": {
                        "passed": True, "duration_seconds": 42.27}},
                },
                "ai_quality_evaluation": {
                    "scores": {"overall_quality": 85},
                    "scenes": [
                        {"scene": n, "regenerate": n in failed,
                         "realism_score": 40 if n in failed else 90}
                        for n in (1, 2, 3)
                    ],
                },
            }, f, ensure_ascii=False)

    return path


class TestStatusIsDerived(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def test_no_script_is_a_draft(self):
        path = _project(self.root, "p1", script=False, evaluated=False)

        self.assertEqual(workflow.status_for(path), workflow.DRAFT)

    def test_a_script_without_an_evaluation_is_still_generating(self):
        path = _project(self.root, "p2", evaluated=False)

        self.assertEqual(workflow.status_for(path), workflow.GENERATING)

    def test_an_evaluated_project_with_no_failures_is_inspection(self):
        path = _project(self.root, "p3")

        self.assertEqual(workflow.status_for(path), workflow.INSPECTION)

    def test_failed_scenes_mean_regeneration_is_needed(self):
        path = _project(self.root, "p4", failed=(2,))

        self.assertEqual(workflow.status_for(path), workflow.NEEDS_REGENERATION)

    def test_a_running_job_wins_over_everything(self):
        """지금 돌고 있는 것이 가장 최신 사실이다."""

        path = _project(self.root, "p5", failed=(2,))

        self.assertEqual(
            workflow.status_for(path, running=True), workflow.GENERATING,
        )

    def test_an_approval_wins_over_the_derived_status(self):
        path = _project(self.root, "p6")

        self.assertEqual(
            workflow.status_for(path, stored={"status": workflow.APPROVED}),
            workflow.APPROVED,
        )

    def test_a_missing_project_is_a_draft_not_a_crash(self):
        self.assertEqual(
            workflow.status_for(os.path.join(self.root, "nope")),
            workflow.DRAFT,
        )


class TestApprovalIsStoredOutsideTheProject(unittest.TestCase):
    """생산 산출물은 손대지 않는다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = os.path.join(self._tmp.name, "store", "workflow.json")
        self.root = os.path.join(self._tmp.name, "out")
        os.makedirs(self.root)

    def test_approving_writes_only_to_the_store(self):
        path = _project(self.root, "p1")
        before = sorted(os.listdir(path))

        workflow.approve("p1", self.store)

        self.assertEqual(sorted(os.listdir(path)), before)
        self.assertTrue(os.path.exists(self.store))

    def test_an_approval_survives_a_reload(self):
        workflow.approve("p1", self.store)

        stored = workflow.load_store(self.store)

        self.assertEqual(stored["p1"]["status"], workflow.APPROVED)
        self.assertTrue(stored["p1"]["approved_at"])

    def test_approving_twice_keeps_the_first_timestamp(self):
        workflow.approve("p1", self.store)
        first = workflow.load_store(self.store)["p1"]["approved_at"]

        workflow.approve("p1", self.store)

        self.assertEqual(
            workflow.load_store(self.store)["p1"]["approved_at"], first,
        )

    def test_unapproving_removes_the_decision(self):
        workflow.approve("p1", self.store)
        workflow.unapprove("p1", self.store)

        self.assertNotIn("p1", workflow.load_store(self.store))

    def test_a_missing_store_reads_as_empty(self):
        self.assertEqual(workflow.load_store(self.store), {})

    def test_a_corrupt_store_reads_as_empty_not_a_crash(self):
        os.makedirs(os.path.dirname(self.store), exist_ok=True)
        with open(self.store, "w", encoding="utf-8") as f:
            f.write("{ broken")

        self.assertEqual(workflow.load_store(self.store), {})

    def test_a_path_like_project_id_is_rejected(self):
        with self.assertRaises(ValueError):
            workflow.approve("../../etc", self.store)


class TestQueue(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "out")
        os.makedirs(self.root)
        self.store = os.path.join(self._tmp.name, "workflow.json")

        _project(self.root, "20260101_000001")
        _project(self.root, "20260101_000002", failed=(2,))

    def _queue(self):
        return workflow.queue(self.root, self.store)

    def test_every_project_appears_once(self):
        self.assertEqual(len(self._queue()), 2)

    def test_newest_first(self):
        self.assertEqual(
            [p["project_id"] for p in self._queue()],
            ["20260101_000002", "20260101_000001"],
        )

    def test_the_columns_the_epic_asked_for_are_present(self):
        row = self._queue()[0]

        for field in ("project_id", "topic", "created_at", "duration",
                      "quality", "status", "failed_scenes"):
            with self.subTest(field=field):
                self.assertIn(field, row)

    def test_duration_comes_from_the_existing_report(self):
        self.assertEqual(self._queue()[0]["duration"], 42.27)

    def test_created_time_comes_from_the_project_id(self):
        row = [p for p in self._queue()
               if p["project_id"] == "20260101_000001"][0]

        self.assertEqual(row["created_at"], "2026-01-01 00:00:01")

    def test_an_unparseable_id_reports_unknown(self):
        _project(self.root, "not_a_timestamp")

        row = [p for p in self._queue()
               if p["project_id"] == "not_a_timestamp"][0]

        self.assertIsNone(row["created_at"])

    def test_missing_metadata_is_null_never_invented(self):
        """"Unknown"은 화면이 붙이는 말이고, 여기서는 None으로 둔다.
        0이나 빈 문자열을 넣으면 화면이 그것을 값으로 읽는다."""

        path = _project(self.root, "20260101_000003", evaluated=False)

        row = [p for p in workflow.queue(self.root, self.store)
               if p["project_id"] == "20260101_000003"][0]

        self.assertIsNone(row["duration"])
        self.assertIsNone(row["quality"])

    def test_a_directory_without_project_json_is_skipped(self):
        os.makedirs(os.path.join(self.root, "images"))

        self.assertEqual(len(self._queue()), 2)

    def test_the_approved_status_shows_in_the_queue(self):
        workflow.approve("20260101_000001", self.store)

        row = [p for p in self._queue()
               if p["project_id"] == "20260101_000001"][0]

        self.assertEqual(row["status"], workflow.APPROVED)

    def test_a_running_project_is_marked_generating(self):
        rows = workflow.queue(
            self.root, self.store, running={"20260101_000001"},
        )
        row = [p for p in rows if p["project_id"] == "20260101_000001"][0]

        self.assertEqual(row["status"], workflow.GENERATING)


class TestFiltering(unittest.TestCase):

    def _rows(self):
        return [
            {"project_id": "a", "status": workflow.APPROVED},
            {"project_id": "b", "status": workflow.NEEDS_REGENERATION},
            {"project_id": "c", "status": workflow.INSPECTION},
        ]

    def test_all_returns_everything(self):
        self.assertEqual(len(workflow.filter_rows(self._rows(), "all")), 3)

    def test_a_status_filter_narrows(self):
        rows = workflow.filter_rows(self._rows(), workflow.APPROVED)

        self.assertEqual([r["project_id"] for r in rows], ["a"])

    def test_published_is_empty_because_upload_does_not_exist(self):
        """업로드 경로가 없으므로 Published에 도달할 방법이 없다.
        필터는 있고 결과는 비어 있는 것이 사실이다."""

        rows = workflow.filter_rows(self._rows(), workflow.PUBLISHED)

        self.assertEqual(rows, [])

    def test_an_unknown_filter_is_rejected(self):
        with self.assertRaises(ValueError):
            workflow.filter_rows(self._rows(), "whatever")


class TestNoEngineIsInvoked(unittest.TestCase):
    """순수 workflow 계층 - 생성도 재생성도 여기서 일어나지 않는다."""

    def test_the_module_imports_no_engine(self):
        import ast

        source = open(workflow.__file__, encoding="utf-8").read()
        tree = ast.parse(source)

        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.update(f"{node.module}.{a.name}" for a in node.names)

        for forbidden in ("regeneration_service", "factory_service",
                          "image_service", "quality_service", "pipeline"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in name for name in names), forbidden,
                )


if __name__ == "__main__":
    unittest.main()
