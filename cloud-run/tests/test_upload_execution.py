"""
Sprint149 - 올리는 동안과 실패한 뒤 (Epic 56, Phase 26).

Sprint148이 승인까지 왔다. 이번에는 그 뒤다 - 올리는 중과, 실패했을
때 다시 하는 길.

무엇을 저장하고 무엇을 읽는가
-----------------------------
    사람의 결정   승인 · 다시 시도하라는 요청
    실행 사실     지금 도는 작업(시작 시각)
    결과          youtube_upload_result.json(성공 여부·오류·완료 시각)

완료 시각을 따로 적지 않는다. 결과 파일이 쓰인 때가 곧 그때다 -
같은 사실을 두 곳에 두면 갈린다.

다시 시도가 새 승인을 만들지 않는다
-----------------------------------
이미 받아 둔 승인을 그대로 쓰고 "언제 다시 하라고 했는지"만 적는다.
그 시각보다 오래된 실패는 지난 일이 되어 상태가 Approved로 돌아간다.

결과 파일은 지우지 않는다 - 무엇이 왜 실패했는지는 남아 있어야
다음 사람이 읽는다.

올리기 전에 본다
----------------
승인 · 영상 · 메타데이터. 앞 관문에서 막히면 작업 자체가 시작되지
않는다. studio_upload도 플래그와 승인을 다시 본다 - 두 번 보는 것이
맞다. 이 자리는 화면이 부르는 입구일 뿐이고 실제 안전장치는 그쪽이다.
"""

import json
import os
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import (
    metadata_service, publish_gate, studio_upload, studio_workflow,
)

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)

QUEUE_PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "queue.html",
)


def _script(path=PAGE):
    with open(path, encoding="utf-8") as f:
        page = f.read()
    return page[page.index("<script>"):]


def _function(name, path=PAGE):
    script = _script(path)
    block = script[script.index(f"function {name}("):]
    end = block.find("\nfunction ", 1)

    return block if end < 0 else block[:end]


def _project(ready=True):
    path = tempfile.mkdtemp()

    with open(os.path.join(path, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"title": "무릎 스트레칭", "scenes": [
            {"scene": 1, "narration": "천천히 하십시오.", "image_prompt": "k"}
        ]}, f, ensure_ascii=False)

    with open(os.path.join(path, "project.json"), "w", encoding="utf-8") as f:
        json.dump({"topic": "무릎"}, f, ensure_ascii=False)

    with open(os.path.join(path, "quality_report.json"), "w",
              encoding="utf-8") as f:
        json.dump({}, f)

    if ready:
        metadata_service.generate_publish_package(path)
        os.makedirs(os.path.join(path, "video"), exist_ok=True)
        open(os.path.join(path, publish_gate.FINAL_VIDEO), "wb").close()

    return path


def _store():
    return os.path.join(tempfile.mkdtemp(), "workflow.json")


def _result(path, outcome, error=None, url=None):
    with open(os.path.join(path, "youtube_upload_result.json"), "w",
              encoding="utf-8") as f:
        json.dump({"outcome": outcome, "error": error, "url": url}, f,
                  ensure_ascii=False)


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _call_upload(path, store):
    import app.routers.studio as studio_router

    with patch.object(studio_router, "_project_path",
                      lambda project_id: path):
        with patch.object(studio_router, "_workflow_store", lambda: store):
            with patch("app.services.studio_jobs.start_upload",
                       return_value="job-1") as start:
                response = _client().post("/studio/api/projects/p1/upload")

    return response, start


class TestOnlyApprovedCanUpload(unittest.TestCase):

    def test_only_approved_can_upload(self):
        path, store = _project(), _store()

        response, start = _call_upload(path, store)

        self.assertEqual(response.status_code, 400)
        self.assertIn("승인된", response.json()["detail"])
        start.assert_not_called()

    def test_an_approved_one_starts(self):
        path, store = _project(), _store()

        studio_workflow.approve("p1", store)

        response, start = _call_upload(path, store)

        self.assertEqual(response.status_code, 200)
        start.assert_called_once()

    def test_a_request_alone_is_not_enough(self):
        """요청은 승인이 아니다."""

        path, store = _project(), _store()

        studio_workflow.request_upload("p1", store)

        response, start = _call_upload(path, store)

        self.assertEqual(response.status_code, 400)
        start.assert_not_called()

    def test_the_upload_service_still_checks_it_too(self):
        """두 번 보는 것이 맞다 - 실제 안전장치는 그쪽이다."""

        with open(studio_upload.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("if not is_approved(", source)
        self.assertIn("ENABLE_YOUTUBE_UPLOAD", source)


class TestUploadNeverRunsWithoutVideo(unittest.TestCase):

    def test_upload_never_runs_without_video(self):
        path, store = _project(ready=False), _store()

        studio_workflow.approve("p1", store)

        response, start = _call_upload(path, store)

        self.assertEqual(response.status_code, 400)
        self.assertIn("영상이 없습니다", response.json()["detail"])
        start.assert_not_called()

    def test_it_stops_without_metadata_too(self):
        path, store = _project(), _store()

        os.remove(os.path.join(path, publish_gate.PACKAGE_FILENAME))
        studio_workflow.approve("p1", store)

        response, start = _call_upload(path, store)

        self.assertEqual(response.status_code, 400)
        self.assertIn("메타데이터가 없습니다", response.json()["detail"])
        start.assert_not_called()

    def test_an_empty_title_stops_it(self):
        path, store = _project(), _store()

        publish_gate.save_edits(path, {"title": "  "})
        studio_workflow.approve("p1", store)

        response, start = _call_upload(path, store)

        self.assertEqual(response.status_code, 400)
        start.assert_not_called()


class TestUploadStateChanges(unittest.TestCase):

    def test_upload_state_changes(self):
        """Approved -> Uploading -> Done."""

        path, store = _project(), _store()

        studio_workflow.approve("p1", store)
        stored = studio_workflow.load_store(store).get("p1")

        self.assertEqual(studio_workflow.status_for(path, stored),
                         studio_workflow.APPROVED)

        self.assertEqual(
            studio_workflow.status_for(path, stored, uploading=True),
            studio_workflow.UPLOADING)

        _result(path, "uploaded", url="https://youtu.be/x")

        self.assertEqual(studio_workflow.status_for(path, stored),
                         studio_workflow.PUBLISHED)

    def test_a_failure_becomes_failed(self):
        path, store = _project(), _store()

        studio_workflow.approve("p1", store)
        _result(path, "failed", error="quota 초과")

        self.assertEqual(
            studio_workflow.status_for(
                path, studio_workflow.load_store(store).get("p1")),
            studio_workflow.UPLOAD_FAILED)

    def test_the_start_time_comes_from_the_job(self):
        from app.services import studio_jobs

        recent = studio_jobs.recent(1)

        # 작업이 하나도 없을 수 있다 - 키가 있는지만 본다.
        studio_jobs._new_job("j", None, None, "p1", "/x")

        self.assertIn("started_at", studio_jobs._new_job(
            "j2", None, None, "p1", "/x"))

    def test_the_finish_time_comes_from_the_result_file(self):
        """따로 적지 않는다 - 파일이 쓰인 때가 곧 그때다."""

        path = _project()

        _result(path, "uploaded", url="https://youtu.be/x")

        row = studio_workflow._upload_row(path)

        self.assertTrue(row["finished_at"])

    def test_no_attempt_means_no_row(self):
        path = _project()

        self.assertIsNone(studio_workflow._upload_row(path))


class TestUploadErrorIsVisible(unittest.TestCase):

    def test_upload_error_is_visible(self):
        path = _project()

        _result(path, "failed", error="quota 초과")

        row = studio_workflow._upload_row(path)

        self.assertEqual(row["outcome"], "failed")
        self.assertEqual(row["error"], "quota 초과")

    def test_the_queue_row_carries_it(self):
        root = tempfile.mkdtemp()
        path = os.path.join(root, "20260101_000001")

        os.makedirs(path)
        for name in ("script.json", "project.json", "quality_report.json"):
            with open(os.path.join(path, name), "w", encoding="utf-8") as f:
                json.dump({}, f)

        _result(path, "failed", error="quota 초과")

        rows = studio_workflow.queue(root, _store())

        self.assertEqual(rows[0]["upload"]["error"], "quota 초과")
        self.assertTrue(rows[0]["upload"]["finished_at"])

    def test_the_queue_screen_shows_it(self):
        with open(QUEUE_PAGE, encoding="utf-8") as f:
            page = f.read()

        self.assertIn("r.upload.error", page)
        self.assertIn("r.upload.finished_at", page)
        self.assertIn("r.started_at", page)


class TestFailedUploadCanRetry(unittest.TestCase):

    def test_failed_upload_can_retry(self):
        path, store = _project(), _store()

        studio_workflow.approve("p1", store)
        _result(path, "failed", error="quota 초과")

        time.sleep(1.1)
        studio_workflow.retry_upload("p1", store)

        self.assertEqual(
            studio_workflow.status_for(
                path, studio_workflow.load_store(store).get("p1")),
            studio_workflow.APPROVED)

    def test_it_keeps_the_approval_it_already_had(self):
        """새 승인 체계를 만들지 않는다."""

        path, store = _project(), _store()

        approved = studio_workflow.approve("p1", store)["approved_at"]
        _result(path, "failed", error="x")

        time.sleep(1.1)
        studio_workflow.retry_upload("p1", store)

        stored = studio_workflow.load_store(store)["p1"]

        self.assertEqual(stored["status"], studio_workflow.APPROVED)
        self.assertEqual(stored["approved_at"], approved)
        self.assertTrue(stored["retried_at"])

    def test_it_keeps_the_error_on_disk(self):
        """무엇이 왜 실패했는지는 남아 있어야 한다."""

        path, store = _project(), _store()

        studio_workflow.approve("p1", store)
        _result(path, "failed", error="quota 초과")

        time.sleep(1.1)
        studio_workflow.retry_upload("p1", store)

        self.assertTrue(os.path.exists(
            os.path.join(path, "youtube_upload_result.json")))
        self.assertEqual(
            studio_workflow._upload_row(path)["error"], "quota 초과")

    def test_a_new_result_counts_again(self):
        path, store = _project(), _store()

        studio_workflow.approve("p1", store)
        _result(path, "failed", error="x")

        time.sleep(1.1)
        studio_workflow.retry_upload("p1", store)
        _result(path, "uploaded", url="https://youtu.be/x")

        self.assertEqual(
            studio_workflow.status_for(
                path, studio_workflow.load_store(store).get("p1")),
            studio_workflow.PUBLISHED)

    def test_retrying_without_approval_is_refused(self):
        store = _store()

        with self.assertRaises(ValueError):
            studio_workflow.retry_upload("p1", store)

    def test_can_retry_needs_all_three(self):
        approved = {"status": studio_workflow.APPROVED}

        self.assertTrue(studio_workflow.can_retry(
            studio_workflow.UPLOAD_FAILED, approved, True))

        self.assertFalse(studio_workflow.can_retry(
            studio_workflow.UPLOAD_FAILED, approved, False))
        self.assertFalse(studio_workflow.can_retry(
            studio_workflow.UPLOAD_FAILED, {}, True))
        self.assertFalse(studio_workflow.can_retry(
            studio_workflow.APPROVED, approved, True))

    def test_the_endpoint_does_it(self):
        import app.routers.studio as studio_router

        path, store = _project(), _store()

        studio_workflow.approve("p1", store)
        _result(path, "failed", error="x")

        time.sleep(1.1)

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            with patch.object(studio_router, "_workflow_store",
                              lambda: store):
                response = _client().post(
                    "/studio/api/projects/p1/retry-upload")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            studio_workflow.status_for(
                path, studio_workflow.load_store(store).get("p1")),
            studio_workflow.APPROVED)

    def test_the_screens_offer_it(self):
        with open(QUEUE_PAGE, encoding="utf-8") as f:
            queue_page = f.read()

        self.assertIn("다시 시도", queue_page)
        self.assertIn("retry-upload", queue_page)
        self.assertIn("r.can_retry", queue_page)

        self.assertIn("다시 시도", _function("publishButtonState"))
        self.assertIn("retry-upload", _function("publishAction"))


class TestNothingForbiddenMoved(unittest.TestCase):

    def _constants(self, module):
        import ast

        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_the_youtube_call_did_not_change(self):
        from app.services import youtube_upload_step_service

        self.assertNotIn(
            "retried_at", self._constants(youtube_upload_step_service))
        self.assertNotIn(
            "finished_at", self._constants(youtube_upload_step_service))

    def test_the_upload_service_did_not_change(self):
        self.assertNotIn("retried_at", self._constants(studio_upload))
        self.assertNotIn("can_retry", self._constants(studio_upload))

    def test_the_render_and_pipeline_did_not_change(self):
        import app.pipeline.pipeline as pipeline
        from app.services import video_builder

        for module in (pipeline, video_builder):
            with self.subTest(module=module.__name__):
                self.assertNotIn("retried_at", self._constants(module))

    def test_the_steps_did_not_change(self):
        from app.steps import step01_script, step05_video

        for module in (step01_script, step05_video):
            with self.subTest(module=module.__name__):
                self.assertNotIn("retried_at", self._constants(module))


class TestTheHandlersStillLineUp(unittest.TestCase):

    def test_the_queue_handlers_are_declared(self):
        with open(QUEUE_PAGE, encoding="utf-8") as f:
            page = f.read()

        declared = set(re.findall(
            r"(?:async\s+)?function\s+(\w+)\s*\(", _script(QUEUE_PAGE)))
        wired = set(re.findall(r'onclick="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])

    def test_the_studio_handlers_are_declared(self):
        with open(PAGE, encoding="utf-8") as f:
            page = f.read()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", _script()))
        wired = set(re.findall(
            r'on(?:click|change|input|timeupdate)="(\w+)\(', page))

        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
