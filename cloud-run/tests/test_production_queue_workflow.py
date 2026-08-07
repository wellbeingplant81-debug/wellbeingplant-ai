"""
Sprint148 - 올리기 전에 사람이 승인한다 (Epic 56, Phase 25).

Production Queue는 Sprint84부터 있었다. 이번에 더한 것은 둘뿐이다.

    업로드 요청   사람이 "올리겠다"고 한 것
    거절 사유     사람이 왜 안 된다고 했는지

둘 다 파일에서 유도할 수 없는 판단이라 저장한다 - 승인과 같은
부류다. 나머지는 예전처럼 산출물에서 읽는다.

새 상태를 저장하지 않는다
-------------------------
    UPLOADING   도는 작업이 곧 사실이다. 저장하면 죽은 작업이 영원히
                "올리는 중"으로 남는다
    DONE·FAILED youtube_upload_result.json이 말한다(Sprint92)
    READY       산출물이 다 있으면 그것이다(inspection)

사양의 DRAFT와 다른 점
----------------------
사양은 "거절하면 DRAFT로"라고 했지만, 이 저장소에서 DRAFT는
"script.json이 없다"는 뜻이다. 대본과 영상이 멀쩡한 프로젝트를
DRAFT라고 적으면 산출물과 다른 말을 하는 것이 된다.

그래서 거절은 요청을 거두고 사유를 남긴다 - 상태는 산출물이 말하는
곳(Ready)으로 돌아간다. 사유는 화면에 남는다.

버튼은 올리지 않는다
--------------------
요청 버튼은 큐에 올려 달라고 말할 뿐이고, 업로드 버튼은 승인된
뒤에만 뜬다. 실제로 올릴지는 예전처럼 studio_upload가
ENABLE_YOUTUBE_UPLOAD와 승인으로 정한다.
"""

import json
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services import metadata_service, publish_gate, studio_workflow

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
    """Sprint147의 검사를 통과하는 프로젝트."""

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


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


class TestPublishCreatesQueueItem(unittest.TestCase):

    def test_publish_creates_queue_item(self):
        path, store = _project(), _store()

        studio_workflow.request_upload("p1", store)

        self.assertEqual(
            studio_workflow.status_for(path, studio_workflow.load_store(
                store).get("p1")),
            studio_workflow.WAITING_APPROVAL)

    def test_it_remembers_when_it_was_asked(self):
        store = _store()

        studio_workflow.request_upload("p1", store)

        self.assertTrue(
            studio_workflow.load_store(store)["p1"]["requested_at"])

    def test_asking_twice_keeps_the_first_time(self):
        """언제 요청했는지가 기록의 요점이다."""

        store = _store()

        first = studio_workflow.request_upload("p1", store)["requested_at"]
        again = studio_workflow.request_upload("p1", store)["requested_at"]

        self.assertEqual(first, again)

    def test_it_never_pulls_an_approved_one_back(self):
        store = _store()

        studio_workflow.approve("p1", store)
        studio_workflow.request_upload("p1", store)

        self.assertEqual(
            studio_workflow.load_store(store)["p1"]["status"],
            studio_workflow.APPROVED)

    def test_the_endpoint_refuses_what_is_not_ready(self):
        """제목도 영상도 없는 것을 큐에 올리면 무엇을 승인하는지 모른다."""

        import app.routers.studio as studio_router

        path = _project(ready=False)

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            response = _client().post(
                "/studio/api/projects/p1/request-upload")

        self.assertEqual(response.status_code, 400)
        self.assertIn("영상이 없습니다", response.json()["detail"])

    def test_the_endpoint_creates_it_when_ready(self):
        import app.routers.studio as studio_router

        path, store = _project(), _store()

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            with patch.object(studio_router, "_workflow_store",
                              lambda: store):
                response = _client().post(
                    "/studio/api/projects/p1/request-upload")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            studio_workflow.load_store(store)["p1"]["status"],
            studio_workflow.WAITING_APPROVAL)


class TestApprovalChangesStatus(unittest.TestCase):

    def test_approval_changes_status(self):
        path, store = _project(), _store()

        studio_workflow.request_upload("p1", store)
        studio_workflow.approve("p1", store)

        self.assertEqual(
            studio_workflow.status_for(path, studio_workflow.load_store(
                store).get("p1")),
            studio_workflow.APPROVED)

    def test_the_new_states_are_known(self):
        for name in ("waiting_approval", "uploading"):
            with self.subTest(name=name):
                self.assertIn(name, studio_workflow.STATUSES)
                self.assertIn(name, studio_workflow.LABELS)

    def test_uploading_is_derived_not_stored(self):
        """죽은 작업이 영원히 "올리는 중"으로 남으면 안 된다."""

        path, store = _project(), _store()

        studio_workflow.approve("p1", store)
        stored = studio_workflow.load_store(store).get("p1")

        self.assertEqual(
            studio_workflow.status_for(path, stored, uploading=True),
            studio_workflow.UPLOADING)

        self.assertNotIn(
            studio_workflow.UPLOADING, studio_workflow.STORED_STATUSES)

    def test_only_human_decisions_are_stored(self):
        self.assertEqual(
            studio_workflow.STORED_STATUSES,
            (studio_workflow.WAITING_APPROVAL, studio_workflow.APPROVED))

    def test_an_upload_result_still_wins(self):
        """올라간 사실은 승인보다 나중의 일이다."""

        path, store = _project(), _store()

        studio_workflow.approve("p1", store)

        with open(os.path.join(path, "youtube_upload_result.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"outcome": "uploaded", "url": "http://x"}, f)

        self.assertEqual(
            studio_workflow.status_for(path, studio_workflow.load_store(
                store).get("p1")),
            studio_workflow.PUBLISHED)


class TestRejectionKeepsReason(unittest.TestCase):

    def test_rejection_keeps_reason(self):
        store = _store()

        studio_workflow.request_upload("p1", store)
        studio_workflow.reject("p1", store, "제목이 어색합니다")

        stored = studio_workflow.load_store(store)["p1"]

        self.assertEqual(stored["rejection_reason"], "제목이 어색합니다")
        self.assertTrue(stored["rejected_at"])

    def test_rejecting_takes_the_request_back(self):
        path, store = _project(), _store()

        studio_workflow.request_upload("p1", store)
        studio_workflow.reject("p1", store, "다시 보십시오")

        self.assertEqual(
            studio_workflow.status_for(path, studio_workflow.load_store(
                store).get("p1")),
            studio_workflow.INSPECTION)

    def test_an_empty_reason_is_allowed(self):
        store = _store()

        studio_workflow.reject("p1", store, "")

        self.assertEqual(
            studio_workflow.load_store(store)["p1"]["rejection_reason"], "")

    def test_the_endpoint_keeps_it(self):
        import app.routers.studio as studio_router

        path, store = _project(), _store()

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            with patch.object(studio_router, "_workflow_store",
                              lambda: store):
                response = _client().post(
                    "/studio/api/projects/p1/reject",
                    json={"reason": "설명이 짧습니다"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            studio_workflow.load_store(store)["p1"]["rejection_reason"],
            "설명이 짧습니다")

    def test_the_queue_screen_shows_it(self):
        with open(QUEUE_PAGE, encoding="utf-8") as f:
            page = f.read()

        self.assertIn("rejection_reason", page)
        self.assertIn("거절 사유", page)
        self.assertIn("function reject(", page)


class TestUploadButtonDoesNotDirectUpload(unittest.TestCase):

    def test_upload_button_does_not_direct_upload(self):
        """요청은 요청일 뿐이다."""

        block = _function("publishAction")

        self.assertIn("request-upload", block)
        self.assertIn('action === "upload"', block)

    def test_requesting_starts_no_job(self):
        import app.routers.studio as studio_router

        path, store = _project(), _store()

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            with patch.object(studio_router, "_workflow_store",
                              lambda: store):
                with patch("app.services.studio_jobs.start_upload") as start:
                    _client().post("/studio/api/projects/p1/request-upload")

        start.assert_not_called()

    def test_the_upload_path_is_still_the_only_one(self):
        from app.main import app

        upload_paths = sorted(
            path for path in app.openapi()["paths"] if "upload" in path
        )

        # Sprint149 - 다시 시도하는 자리가 늘었다. 실제로 올리는 자리는
        # 여전히 /upload 하나뿐이다.
        self.assertEqual(upload_paths, [
            "/studio/api/projects/{project_id}/request-upload",
            "/studio/api/projects/{project_id}/retry-upload",
            "/studio/api/projects/{project_id}/upload",
        ])

    def test_the_gate_still_decides(self):
        from app.services import studio_upload

        with open(studio_upload.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("ENABLE_YOUTUBE_UPLOAD", source)
        self.assertIn("def is_approved(", source)

    def test_the_button_says_where_it_is(self):
        block = _function("publishButtonState")

        for word in ("승인 대기", "업로드 가능", "업로드 중", "게시 완료"):
            with self.subTest(word=word):
                self.assertIn(word, block)

    def test_the_button_reads_the_server_not_its_own_guess(self):
        block = _function("publishButtonState")

        self.assertIn("state.queue_status", block)

    def test_no_new_upload_engine_was_written(self):
        from app.services import studio_upload

        self.assertNotIn("request_upload", open(
            studio_upload.__file__, encoding="utf-8").read())


class TestQueueSurvivesReload(unittest.TestCase):

    def test_queue_survives_reload(self):
        """새로고침을 넘어 살아남아야 한다 - 사람이 내린 판단이므로."""

        store = _store()

        studio_workflow.request_upload("p1", store)

        # 저장소를 다시 읽는다. 프로세스가 죽었다 살아난 것과 같다.
        reloaded = studio_workflow.load_store(store)

        self.assertEqual(reloaded["p1"]["status"],
                         studio_workflow.WAITING_APPROVAL)

    def test_the_reason_survives_too(self):
        store = _store()

        studio_workflow.reject("p1", store, "다시 보십시오")

        self.assertEqual(
            studio_workflow.load_store(store)["p1"]["rejection_reason"],
            "다시 보십시오")

    def test_it_lives_outside_the_project(self):
        """생산 산출물은 한 바이트도 손대지 않는다."""

        path, store = _project(), _store()

        studio_workflow.request_upload("p1", store)

        self.assertFalse(os.path.exists(
            os.path.join(path, "workflow.json")))
        self.assertFalse(store.startswith(path))

    def test_a_broken_store_does_not_kill_the_queue(self):
        store = _store()

        os.makedirs(os.path.dirname(store), exist_ok=True)
        with open(store, "w", encoding="utf-8") as f:
            f.write("{깨진")

        self.assertEqual(studio_workflow.load_store(store), {})


class TestNothingForbiddenMoved(unittest.TestCase):

    def _constants(self, module):
        import ast

        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_the_render_and_pipeline_did_not_change(self):
        import app.pipeline.pipeline as pipeline
        from app.services import scene_order, video_builder

        for module in (pipeline, video_builder, scene_order):
            with self.subTest(module=module.__name__):
                self.assertNotIn(
                    "waiting_approval", self._constants(module))

    def test_the_steps_did_not_change(self):
        from app.steps import step01_script, step05_video

        for module in (step01_script, step05_video):
            with self.subTest(module=module.__name__):
                self.assertNotIn(
                    "waiting_approval", self._constants(module))

    def test_the_providers_did_not_change(self):
        from app.services import provider_selection

        self.assertNotIn(
            "waiting_approval", self._constants(provider_selection))

    def test_the_workflow_still_calls_no_engine(self):
        """승인은 workflow 상태만 바꾼다."""

        import ast

        with open(studio_workflow.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")

        for name in imported:
            with self.subTest(imported=name):
                self.assertNotIn("app.steps", name)
                self.assertNotIn("app.pipeline", name)


class TestTheHandlersStillLineUp(unittest.TestCase):

    def test_every_handler_the_studio_markup_calls_is_declared(self):
        with open(PAGE, encoding="utf-8") as f:
            page = f.read()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", _script()))
        wired = set(re.findall(
            r'on(?:click|change|input|timeupdate)="(\w+)\(', page))

        self.assertEqual(sorted(wired - declared), [])

    def test_every_handler_the_queue_markup_calls_is_declared(self):
        with open(QUEUE_PAGE, encoding="utf-8") as f:
            page = f.read()

        declared = set(re.findall(
            r"(?:async\s+)?function\s+(\w+)\s*\(", _script(QUEUE_PAGE)))
        wired = set(re.findall(r'onclick="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
