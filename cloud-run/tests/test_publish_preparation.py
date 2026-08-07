"""
Sprint147 - 올리기 전에 사람이 고친다 (Epic 56, Phase 24).

Render가 끝나면 publish_package.json이 놓인다. 지금까지 화면은 그것을
읽기만 했다 - 제목이 마음에 들지 않아도 고칠 자리가 없었다.

무엇을 고칠 수 있는가
---------------------
    title · description · tags

셋뿐이다. 나머지는 만들어진 것이거나(category_id, duration) 다른
자리가 정한 것이라(privacy_status, playlist_title) 화면이 손댈 일이
아니다. 영상도 scene도 여기서 건드리지 않는다.

현재 엔진을 고른 채로 고치면
----------------------------
다시 렌더할 때 metadata_service가 그 자리를 다시 만든다 - current는
"엔진이 만든다"는 뜻이기 때문이다. 그러면 사람이 고친 글이 사라진다.

숨기지 않고 화면이 말한다. 유지하려면 manual을 고르면 된다 -
manual은 놓인 것을 그대로 쓴다(Sprint129).

올리기 버튼은 올리지 않는다
---------------------------
누르면 작업을 걸 뿐이고, 실제로 올릴지는 studio_upload가 정한다
(ENABLE_YOUTUBE_UPLOAD와 Production Queue 승인). 화면이 그 판정을
흉내 내지 않는다.
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

from app.services import metadata_service, provider_selection, publish_gate

PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "static", "studio.html",
)


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _script():
    page = _page()
    return page[page.index("<script>"):]


def _function(name):
    script = _script()
    block = script[script.index(f"function {name}("):]
    end = block.find("\nfunction ", 1)

    return block if end < 0 else block[:end]


def _project(with_video=True, with_package=True):
    path = tempfile.mkdtemp()

    with open(os.path.join(path, "script.json"), "w", encoding="utf-8") as f:
        json.dump({"title": "무릎 스트레칭", "scenes": [
            {"scene": 1, "narration": "천천히 하십시오.", "image_prompt": "k"}
        ]}, f, ensure_ascii=False)

    with open(os.path.join(path, "project.json"), "w", encoding="utf-8") as f:
        json.dump({"topic": "무릎"}, f, ensure_ascii=False)

    if with_package:
        metadata_service.generate_publish_package(path)

    if with_video:
        os.makedirs(os.path.join(path, "video"), exist_ok=True)
        open(os.path.join(path, publish_gate.FINAL_VIDEO), "wb").close()

    return path


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


class TestPublishPackageEditableFields(unittest.TestCase):

    def test_publish_package_editable_fields(self):
        self.assertEqual(publish_gate.EDITABLE,
                         ("title", "description", "tags"))

    def test_only_those_three_change(self):
        path = _project()
        before = publish_gate.package(path)

        publish_gate.save_edits(path, {
            "title": "사람이 고친 제목",
            "description": "사람이 고친 설명",
            "tags": ["가", "나"],
            # 아래는 만들어진 것들이다 - 보내도 무시해야 한다.
            "category_id": 999,
            "privacy_status": "public",
            "duration": 999.0,
        })

        after = publish_gate.package(path)

        self.assertEqual(after["title"], "사람이 고친 제목")
        self.assertEqual(after["description"], "사람이 고친 설명")
        self.assertEqual(after["tags"], ["가", "나"])

        for key in ("category_id", "privacy_status", "duration"):
            with self.subTest(key=key):
                self.assertEqual(after[key], before[key])

    def test_the_other_keys_survive_untouched(self):
        path = _project()
        before = publish_gate.package(path)

        publish_gate.save_edits(path, {"title": "새 제목"})

        after = publish_gate.package(path)

        self.assertEqual(set(after), set(before))

        for key in before:
            if key == "title":
                continue
            with self.subTest(key=key):
                self.assertEqual(after[key], before[key])

    def test_it_never_creates_a_missing_package(self):
        """빈 껍데기를 남기면 업로드가 그것을 진짜로 읽는다."""

        path = _project(with_package=False)

        with self.assertRaises(ValueError):
            publish_gate.save_edits(path, {"title": "x"})

        self.assertFalse(os.path.exists(
            os.path.join(path, publish_gate.PACKAGE_FILENAME)))

    def test_the_endpoint_saves_them(self):
        import app.routers.studio as studio_router

        path = _project()

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            response = _client().put(
                "/studio/api/review/p1/metadata",
                json={"metadata": {"title": "화면에서 고친 제목",
                                   "tags": ["ㄱ"]}})

        self.assertEqual(response.status_code, 200)

        saved = publish_gate.package(path)

        self.assertEqual(saved["title"], "화면에서 고친 제목")
        self.assertEqual(saved["tags"], ["ㄱ"])

    def test_the_screen_asks_the_server_what_is_editable(self):
        """고칠 수 있는 칸을 화면이 따로 정하면 두 곳이 갈린다."""

        import app.routers.studio as studio_router

        path = _project()

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            state = _client().get("/studio/api/review/p1").json()

        self.assertEqual(state["metadata"]["editable"],
                         list(publish_gate.EDITABLE))

    def test_the_video_and_the_scenes_are_not_touched(self):
        path = _project()

        script_before = open(os.path.join(path, "script.json"),
                             encoding="utf-8").read()

        publish_gate.save_edits(path, {"title": "x", "description": "y"})

        self.assertEqual(
            open(os.path.join(path, "script.json"), encoding="utf-8").read(),
            script_before)
        self.assertTrue(os.path.exists(
            os.path.join(path, publish_gate.FINAL_VIDEO)))


class TestPublishValidationBlocksMissingMetadata(unittest.TestCase):

    def test_publish_validation_blocks_missing_metadata(self):
        path = _project(with_package=False)

        self.assertIn("메타데이터가 없습니다", publish_gate.problems(path))
        self.assertFalse(publish_gate.ready(path))

    def test_a_missing_video_is_named(self):
        path = _project(with_video=False)

        self.assertIn("영상이 없습니다", publish_gate.problems(path))

    def test_an_empty_title_is_named(self):
        path = _project()
        publish_gate.save_edits(path, {"title": "   "})

        self.assertIn("제목을 입력해주세요", publish_gate.problems(path))

    def test_an_empty_description_is_named(self):
        path = _project()
        publish_gate.save_edits(path, {"description": ""})

        self.assertIn("설명을 입력해주세요", publish_gate.problems(path))

    def test_a_ready_project_has_nothing_to_say(self):
        path = _project()

        self.assertEqual(publish_gate.problems(path), [])
        self.assertTrue(publish_gate.ready(path))

    def test_the_screen_is_told_the_problems(self):
        import app.routers.studio as studio_router

        path = _project(with_video=False)

        with patch.object(studio_router, "_project_path",
                          lambda project_id: path):
            state = _client().get("/studio/api/review/p1").json()

        self.assertIn("영상이 없습니다", state["publish_problems"])

    def test_the_screen_shows_them_without_guessing(self):
        block = _function("publishButtonState")

        self.assertIn("state.publish_problems", block)
        self.assertIn("YouTube 업로드 준비 필요", block)
        self.assertIn("업로드 요청", block)


class TestManualMetadataIsPreserved(unittest.TestCase):

    def test_manual_metadata_is_preserved(self):
        """manual은 사람이 쓴다는 뜻이다 - 엔진이 다시 만들지 않는다."""

        path = _project()

        provider_selection.save(path, {"metadata": "manual"})
        publish_gate.save_edits(path, {"title": "사람이 쓴 제목"})

        again = metadata_service.generate_publish_package(path)

        self.assertEqual(again["title"], "사람이 쓴 제목")
        self.assertEqual(publish_gate.package(path)["title"], "사람이 쓴 제목")

    def test_current_regenerates_and_the_screen_says_so(self):
        """
        숨기지 않는다. current는 "엔진이 만든다"는 뜻이라 다시 렌더하면
        사람이 고친 글이 사라진다 - 화면이 그 사실을 말한다.
        """

        path = _project()

        publish_gate.save_edits(path, {"title": "사람이 쓴 제목"})
        again = metadata_service.generate_publish_package(path)

        self.assertNotEqual(again["title"], "사람이 쓴 제목")

        block = _function("metadataProviderLabel")

        self.assertIn("다시 만듭니다", block)
        self.assertIn("직접 입력", block)
        self.assertIn("자동 생성", block)


class TestProviderMetadataSelectionSurvivesRender(unittest.TestCase):

    def test_provider_metadata_selection_survives_render(self):
        path = _project()

        provider_selection.save(path, {"metadata": "manual"})
        metadata_service.generate_publish_package(path)

        self.assertEqual(
            provider_selection.selected(path, "metadata"), "manual")

    def test_it_lives_in_project_json(self):
        path = _project()

        provider_selection.save(path, {"metadata": "manual"})

        with open(os.path.join(path, "project.json"), encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(saved["metadata_provider"], "manual")

    def test_saving_metadata_does_not_move_the_provider(self):
        path = _project()

        provider_selection.save(path, {"metadata": "manual"})
        publish_gate.save_edits(path, {"title": "x"})

        self.assertEqual(
            provider_selection.selected(path, "metadata"), "manual")

    def test_the_screen_reads_the_choice(self):
        block = _function("metadataProviderLabel")

        self.assertIn("state.providers", block)
        self.assertIn("metadata", block)


class TestPublishButtonNeverUploadsDirectly(unittest.TestCase):

    def test_publish_button_never_uploads_directly(self):
        """
        누르면 작업을 걸 뿐이다. 실제로 올릴지는 studio_upload가
        ENABLE_YOUTUBE_UPLOAD와 승인으로 정한다.
        """

        from app.services import studio_upload

        with open(studio_upload.__file__, encoding="utf-8") as f:
            source = f.read()

        self.assertIn("def is_approved(", source)
        self.assertIn("ENABLE_YOUTUBE_UPLOAD", source)

    def test_the_screen_makes_no_upload_call_of_its_own(self):
        script = _script()

        # 올리는 자리는 예전 그대로 하나뿐이다.
        self.assertEqual(script.count("/upload"), 1)
        self.assertIn("reviewUpload", _function("publishPanel"))

    def test_no_new_upload_endpoint_was_added(self):
        from app.main import app

        upload_paths = [
            path for path in app.openapi()["paths"]
            if "upload" in path
        ]

        self.assertEqual(upload_paths,
                         ["/studio/api/projects/{project_id}/upload"])

    def test_the_button_is_off_until_the_checks_pass(self):
        block = _function("publishPanel")

        self.assertIn("button.ready", block)
        self.assertIn("disabled", block)

    def test_it_says_the_queue_still_decides(self):
        block = _function("publishButtonState")

        self.assertIn("Production Queue", block)


class TestNothingForbiddenMoved(unittest.TestCase):

    def _constants(self, module):
        import ast

        with open(module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        return {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_the_metadata_engine_did_not_change(self):
        self.assertNotIn("publish_gate", self._constants(metadata_service))

    def test_the_pipeline_and_steps_did_not_change(self):
        import app.pipeline.pipeline as pipeline
        from app.steps import step01_script, step07_quality

        for module in (pipeline, step01_script, step07_quality):
            with self.subTest(module=module.__name__):
                self.assertNotIn("publish_gate", self._constants(module))

    def test_the_render_did_not_change(self):
        from app.services import scene_order, video_builder

        for module in (video_builder, scene_order):
            with self.subTest(module=module.__name__):
                self.assertNotIn("publish_gate", self._constants(module))

    def test_the_upload_service_did_not_change(self):
        from app.services import studio_upload

        self.assertNotIn("publish_gate", self._constants(studio_upload))


class TestTheHandlersStillLineUp(unittest.TestCase):

    def test_every_handler_the_markup_calls_is_declared(self):
        page = _page()
        script = _script()

        declared = set(re.findall(r"function\s+(\w+)\s*\(", script))
        wired = set(re.findall(
            r'on(?:click|change|input|timeupdate)="(\w+)\(', page))

        self.assertTrue(wired)
        self.assertEqual(sorted(wired - declared), [])


if __name__ == "__main__":
    unittest.main()
