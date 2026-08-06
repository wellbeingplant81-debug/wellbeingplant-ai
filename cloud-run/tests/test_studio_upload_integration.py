"""
Sprint92 - Pipeline Upload Integration (Phase 5).

Sprint89/90/91이 만든 업로드 계층을 실제 제작 흐름에 붙인다.

여기서 지켜야 할 것이 셋이다.

하나. 승인 없이는 올라가지 않는다. 파이프라인 끝에서도 업로드 함수를
부르지만(Acceptance 1), 갓 만든 프로젝트는 승인 상태가 아니므로 거기서는
항상 건너뛴다.

둘. 건너뛴 것과 실패한 것은 다르다. 플래그가 꺼져 있어서 아무 일도
안 한 프로젝트가 "업로드 실패"로 보이면 안 된다.

셋. 업로드 실패는 파이프라인 실패가 아니다. 영상은 이미 다 만들어졌다.
"""

import ast
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

from app import config
from app.services import studio_upload, studio_workflow
from app.services import youtube_upload_step_service as step_service


def _project(root, name, approved_store=None, video=True):
    path = os.path.join(root, name)
    os.makedirs(os.path.join(path, "video"), exist_ok=True)

    with open(os.path.join(path, "project.json"), "w", encoding="utf-8") as f:
        json.dump({"topic": "혈관 건강", "channel": "wellbeing"}, f,
                  ensure_ascii=False)

    with open(os.path.join(path, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"title": "제목", "script": "본문",
                   "scenes": [{"scene": 1}]}, f, ensure_ascii=False)

    with open(os.path.join(path, "quality_report.json"), "w",
              encoding="utf-8") as f:
        json.dump({"ai_quality_evaluation": {
            "scores": {"overall_quality": 85},
            "scenes": [{"scene": 1, "regenerate": False}]}}, f,
            ensure_ascii=False)

    if video:
        with open(os.path.join(path, "video", "final_short.mp4"), "wb") as f:
            f.write(b"mp4")

    if approved_store:
        studio_workflow.approve(name, approved_store)

    return path


def _result(project_path, outcome, **extra):
    payload = {"success": outcome == "uploaded", "outcome": outcome,
               "upload_id": None, "url": None, "error": None,
               "thumbnail_error": None, "playlist_error": None}
    payload.update(extra)
    with open(os.path.join(project_path, step_service.RESULT_FILENAME),
              "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "output")
        os.makedirs(self.root)
        self.store = os.path.join(self._tmp.name, ".workflow", "workflow.json")


class TestTheGateOrder(_Case):
    """플래그가 먼저고, 승인이 그다음이다. 앞에서 막히면 뒤쪽 코드는
    실행되지 않는다."""

    def test_the_flag_is_on_after_pv02_validation(self):
        """PV-02에서 실제 업로드를 확인하고 켰다. 이 플래그가 켜져
        있어도 승인 없이는 올라가지 않는다는 것이 이 클래스의 나머지
        테스트다."""

        self.assertTrue(config.ENABLE_YOUTUBE_UPLOAD)

    def test_an_unapproved_project_is_still_refused_with_the_flag_on(self):
        """플래그를 켠 것이 승인 문까지 연 것은 아니다. 파이프라인이
        영상을 다 만들었다는 사실만으로는 올라가지 않는다."""

        path = _project(self.root, "flagon")

        with patch.object(step_service, "run_youtube_upload_step") as step:
            result = studio_upload.run_upload(path, self.store)

        step.assert_not_called()
        self.assertEqual(result["outcome"], studio_upload.SKIPPED)

    def test_a_disabled_flag_skips_before_anything_else(self):
        path = _project(self.root, "p1", self.store)

        with patch.object(config, "ENABLE_YOUTUBE_UPLOAD", False), \
             patch.object(step_service, "run_youtube_upload_step") as step:
            result = studio_upload.run_upload(path, self.store)

        step.assert_not_called()
        self.assertEqual(result["outcome"], studio_upload.SKIPPED)
        self.assertIn("ENABLE_YOUTUBE_UPLOAD", result["error"])

    def test_an_unapproved_project_is_skipped_even_with_the_flag_on(self):
        path = _project(self.root, "p2")

        with patch.object(config, "ENABLE_YOUTUBE_UPLOAD", True), \
             patch.object(step_service, "run_youtube_upload_step") as step:
            result = studio_upload.run_upload(path, self.store)

        step.assert_not_called()
        self.assertEqual(result["outcome"], studio_upload.SKIPPED)
        self.assertIn("승인", result["error"])

    def test_an_approved_project_reaches_the_upload_step(self):
        path = _project(self.root, "p3", self.store)

        with patch.object(config, "ENABLE_YOUTUBE_UPLOAD", True), \
             patch.object(step_service, "run_youtube_upload_step",
                          return_value={"outcome": "uploaded"}) as step:
            studio_upload.run_upload(path, self.store)

        step.assert_called_once()

    def test_the_topic_and_script_come_from_the_project_on_disk(self):
        path = _project(self.root, "p4", self.store)
        seen = {}

        def _step(topic, project_path, data):
            seen.update(topic=topic, data=data)
            return {"outcome": "uploaded"}

        with patch.object(config, "ENABLE_YOUTUBE_UPLOAD", True), \
             patch.object(step_service, "run_youtube_upload_step", _step):
            studio_upload.run_upload(path, self.store)

        self.assertEqual(seen["topic"], "혈관 건강")
        self.assertEqual(seen["data"]["title"], "제목")
        self.assertEqual(seen["data"]["script"], "본문")


class TestSkippingLeavesNoTrace(_Case):
    """기본값으로 도는 파이프라인이 프로젝트 폴더에 새 파일을 남기면
    기존 산출물 계약이 조용히 바뀐다."""

    def test_a_skip_writes_no_result_file(self):
        path = _project(self.root, "p1")
        before = sorted(os.listdir(path))

        with patch.object(config, "ENABLE_YOUTUBE_UPLOAD", False):
            studio_upload.run_upload(path, self.store)

        self.assertEqual(sorted(os.listdir(path)), before)
        self.assertIsNone(studio_upload.read_result(path))

    def test_an_unapproved_skip_writes_no_result_file_either(self):
        path = _project(self.root, "p2")

        with patch.object(config, "ENABLE_YOUTUBE_UPLOAD", True), \
             patch.object(step_service, "run_youtube_upload_step") as step:
            studio_upload.run_upload(path, self.store)

        step.assert_not_called()
        self.assertFalse(os.path.exists(
            os.path.join(path, step_service.RESULT_FILENAME)))


class TestStatusIsDerivedFromTheUploadArtifact(_Case):
    """Sprint84와 같은 원칙 - 사람이 내린 결정만 저장하고 나머지는
    산출물에서 유도한다. 업로드 성공은 사실이지 판단이 아니다."""

    def test_published_is_not_a_stored_status(self):
        self.assertNotIn(studio_workflow.PUBLISHED,
                         studio_workflow.STORED_STATUSES)

    def test_a_successful_upload_reads_as_published(self):
        path = _project(self.root, "p1", self.store)
        _result(path, "uploaded", url="https://youtu.be/x")

        self.assertEqual(
            studio_workflow.status_for(path, {"status": "approved"}),
            studio_workflow.PUBLISHED,
        )

    def test_a_failed_upload_reads_as_upload_failed(self):
        path = _project(self.root, "p2", self.store)
        _result(path, "failed", error="quotaExceeded")

        self.assertEqual(
            studio_workflow.status_for(path, {"status": "approved"}),
            studio_workflow.UPLOAD_FAILED,
        )

    def test_a_skipped_upload_leaves_the_status_alone(self):
        """플래그가 꺼져 있어 안 올린 프로젝트가 업로드 실패로 보이면
        안 된다."""

        path = _project(self.root, "p3", self.store)
        _result(path, "skipped", error="ENABLE_YOUTUBE_UPLOAD가 꺼져 있습니다.")

        self.assertEqual(
            studio_workflow.status_for(path, {"status": "approved"}),
            studio_workflow.APPROVED,
        )

    def test_no_upload_attempt_leaves_the_status_alone(self):
        path = _project(self.root, "p4")

        self.assertEqual(
            studio_workflow.status_for(path), studio_workflow.INSPECTION,
        )

    def test_a_corrupt_result_file_does_not_crash_the_queue(self):
        path = _project(self.root, "p5")
        with open(os.path.join(path, step_service.RESULT_FILENAME),
                  "w", encoding="utf-8") as f:
            f.write("{ broken")

        self.assertEqual(
            studio_workflow.status_for(path), studio_workflow.INSPECTION,
        )

    def test_a_running_job_still_wins(self):
        path = _project(self.root, "p6")
        _result(path, "uploaded")

        self.assertEqual(
            studio_workflow.status_for(path, running=True),
            studio_workflow.GENERATING,
        )

    def test_the_result_filename_matches_the_step_service(self):
        """workflow는 이 이름을 import하지 않고 다시 적었다(순수 계층을
        유지하려고). 두 이름이 어긋나면 여기서 걸린다."""

        self.assertEqual(
            studio_workflow._UPLOAD_RESULT_FILENAME,
            step_service.RESULT_FILENAME,
        )

    def test_the_outcome_names_match_the_step_service(self):
        self.assertEqual(studio_workflow._UPLOADED, step_service.UPLOADED)
        self.assertEqual(studio_workflow._FAILED, step_service.FAILED)


class TestTheQueueReflectsUpload(_Case):

    def test_upload_failed_is_a_real_queue_status(self):
        self.assertIn(studio_workflow.UPLOAD_FAILED, studio_workflow.STATUSES)
        self.assertEqual(
            studio_workflow.LABELS[studio_workflow.UPLOAD_FAILED],
            "Upload Failed",
        )

    def test_a_published_project_appears_in_the_published_filter(self):
        path = _project(self.root, "20260101_000001", self.store)
        _result(path, "uploaded", url="https://youtu.be/x")

        rows = studio_workflow.queue(self.root, self.store)
        published = studio_workflow.filter_rows(
            rows, studio_workflow.PUBLISHED,
        )

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["project_id"], "20260101_000001")

    def test_the_row_carries_the_url_so_the_screen_can_link_it(self):
        path = _project(self.root, "20260101_000002", self.store)
        _result(path, "uploaded", url="https://youtu.be/abc")

        row = studio_workflow.queue(self.root, self.store)[0]

        self.assertEqual(row["upload"]["url"], "https://youtu.be/abc")

    def test_the_row_carries_the_failure_reason(self):
        path = _project(self.root, "20260101_000003", self.store)
        _result(path, "failed", error="quotaExceeded")

        row = studio_workflow.queue(self.root, self.store)[0]

        self.assertEqual(row["status"], studio_workflow.UPLOAD_FAILED)
        self.assertEqual(row["upload"]["error"], "quotaExceeded")

    def test_a_project_that_was_never_uploaded_has_no_upload_facts(self):
        _project(self.root, "20260101_000004")

        row = studio_workflow.queue(self.root, self.store)[0]

        self.assertIsNone(row["upload"])


class TestFailureDoesNotBreakGeneration(_Case):
    """Acceptance 5 - 영상 생성 성공은 유지된다."""

    def test_an_exception_inside_upload_is_swallowed(self):
        path = _project(self.root, "p1", self.store)

        def _boom(*a, **k):
            raise RuntimeError("network down")

        with patch.object(config, "ENABLE_YOUTUBE_UPLOAD", True), \
             patch.object(step_service, "run_youtube_upload_step", _boom):
            result = studio_upload.run_upload_quietly(path, self.store)

        self.assertEqual(result["outcome"], studio_upload.SKIPPED)
        self.assertIn("network down", result["error"])

    def test_a_failed_upload_keeps_the_video_intact(self):
        path = _project(self.root, "p2", self.store)
        video = os.path.join(path, "video", "final_short.mp4")
        before = os.path.getsize(video)

        _result(path, "failed", error="quotaExceeded")

        self.assertEqual(os.path.getsize(video), before)
        self.assertEqual(
            studio_workflow.status_for(path, {"status": "approved"}),
            studio_workflow.UPLOAD_FAILED,
        )


class TestThePipelineIsWiredButCannotAutoPublish(unittest.TestCase):

    def test_the_pipeline_calls_the_upload_entry_point(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        self.assertIn("run_upload_quietly", source)

    def test_the_pipeline_uses_the_forgiving_entry_point_not_the_raw_one(self):
        """run_upload()를 그대로 부르면 업로드 예외가 파이프라인을
        무너뜨린다. 영상은 이미 다 만들어진 뒤다."""

        import app.pipeline.pipeline as pipeline

        tree = ast.parse(open(pipeline.__file__, encoding="utf-8").read())
        called = {
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }

        self.assertIn("run_upload_quietly", called)
        self.assertNotIn("run_youtube_upload_step", called)

    def test_a_fresh_pipeline_run_can_never_publish_by_itself(self):
        """갓 만든 프로젝트는 승인 상태가 아니다. 검수 전에 올라가면
        되돌릴 수 없다."""

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = os.path.join(tmp.name, "output")
        os.makedirs(root)
        store = os.path.join(tmp.name, "workflow.json")

        path = _project(root, "20260101_000001")

        with patch.object(config, "ENABLE_YOUTUBE_UPLOAD", True), \
             patch.object(step_service, "run_youtube_upload_step") as step:
            result = studio_upload.run_upload_quietly(path, store)

        step.assert_not_called()
        self.assertEqual(result["outcome"], studio_upload.SKIPPED)
        self.assertEqual(
            studio_workflow.status_for(path), studio_workflow.INSPECTION,
        )


class TestTheEngineStaysLight(unittest.TestCase):
    """파이프라인이 studio_upload를 import한다. 그 한 줄 때문에 Upload
    Core와 googleapiclient가 딸려 들어오면 안 된다 - 플래그가 꺼져 있어
    업로드할 생각이 없는 실행에서도 그 비용을 내게 된다.

    처음 구현에서 실제로 그렇게 됐다. outcome 상수를 step service에서
    가져왔더니 그 한 줄이 전부를 끌고 왔다."""

    def _load_pipeline_in_a_clean_interpreter(self):
        import subprocess

        code = (
            "import sys\n"
            "import app.pipeline.pipeline\n"
            "heavy = [m for m in sys.modules if 'providers.upload' in m"
            " or m.startswith('googleapiclient')"
            " or 'youtube_upload_step' in m or 'real_youtube' in m]\n"
            "print(len(heavy))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
        )
        return result

    def test_the_pipeline_does_not_drag_in_the_upload_core(self):
        result = self._load_pipeline_in_a_clean_interpreter()

        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertEqual(result.stdout.strip(), "0", result.stdout)

    def test_studio_upload_imports_nothing_heavy_at_module_level(self):
        tree = ast.parse(
            open(studio_upload.__file__, encoding="utf-8").read(),
        )
        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                top_level.add(node.module or "")
            elif isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)

        for forbidden in ("youtube_upload_step_service", "providers.upload",
                          "real_youtube_runtime", "oauth_manager"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in name for name in top_level), forbidden,
                )


class TestTheStorePathHasOneDefinition(unittest.TestCase):

    def test_the_router_and_the_pipeline_read_the_same_file(self):
        from app.routers import studio as router

        self.assertEqual(
            router._workflow_store(), studio_upload.default_store_path(),
        )

    def test_the_store_lives_outside_the_project_directories(self):
        from app.services import project_service

        self.assertNotIn(
            os.path.normpath(project_service.OUTPUT_ROOT),
            os.path.normpath(studio_upload.default_store_path()),
        )


if __name__ == "__main__":
    unittest.main()
