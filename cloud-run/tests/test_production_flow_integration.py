"""
Sprint107 - 붙여넣은 대본으로 실제 영상을 만든다 (Epic 54, Phase 6).

Sprint105의 화면은 읽어서 보여주는 데서 끝났다. 여기서 그것을 실제
프로젝트로 만들고, 기존 "영상 생성" 버튼이 그 프로젝트를 집어 들게
한다.

Generate 경로를 새로 만들지 않았다. 버튼도 엔드포인트도 하나 그대로고,
project_id라는 선택 인자가 하나 늘었을 뿐이다. 주지 않으면 예전과
완전히 같다 - 그것이 이 스프린트에서 가장 중요한 계약이다.
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

from fastapi.testclient import TestClient

from app.main import app
from app.production.imported_project import create_from_script
from app.services import factory_service, project_service, studio_jobs
from app.steps import step01_script, step01_script_resolve as resolver

client = TestClient(app)

RAW = ('{"title":"붙여넣은 대본","scenes":['
       '{"scene":1,"narration":"첫 문장.","subject":"a man","action":"drinking"},'
       '{"scene":2,"narration":"둘째 문장.","subject":"a man","action":"walking"}]}')


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(project_service, "OUTPUT_ROOT", self._tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestProjectCreation(_Case):

    def test_the_endpoint_creates_a_real_project(self):
        response = client.post("/studio/api/production/project", json={
            "raw": RAW, "topic": "혈관 건강", "channel": "wellbeing",
            "source": "import",
        })

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["project_id"])
        self.assertEqual(body["scene_count"], 2)
        self.assertEqual(body["source"], "import")

    def test_the_folder_structure_is_the_usual_one(self):
        """create_project()를 그대로 부른다 - 타임스탬프 규칙도 폴더
        구조도 예전과 같다."""

        body = client.post("/studio/api/production/project", json={
            "raw": RAW, "topic": "혈관 건강",
        }).json()

        path = os.path.join(self._tmp.name, body["project_id"])

        self.assertEqual(
            sorted(os.listdir(path)),
            ["audio", "images", "project.json", "script.json", "video"],
        )

    def test_the_project_id_is_a_timestamp(self):
        body = client.post("/studio/api/production/project", json={
            "raw": RAW, "topic": "t",
        }).json()

        self.assertRegex(body["project_id"], r"^\d{8}_\d{6}$")

    def test_the_script_is_saved_in_the_engine_format(self):
        """추가 변환 금지 - Chat Import가 만든 것을 그대로 쓴다."""

        body = client.post("/studio/api/production/project", json={
            "raw": RAW, "topic": "t",
        }).json()

        path = os.path.join(self._tmp.name, body["project_id"], "script.json")
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(
            sorted(saved.keys()),
            sorted(["title", "hook", "script", "character", "scenes"]),
        )
        self.assertIn("image_prompt", saved["scenes"][0])

    def test_the_source_is_recorded_in_project_metadata(self):
        for source in ("import", "manual"):
            with self.subTest(source=source):
                body = client.post("/studio/api/production/project", json={
                    "raw": RAW, "topic": "t", "source": source,
                }).json()

                path = os.path.join(
                    self._tmp.name, body["project_id"], "project.json",
                )
                with open(path, encoding="utf-8") as f:
                    metadata = json.load(f)

                self.assertEqual(metadata["production_source"], source)
                # create_project()가 쓰던 것들은 그대로 있다.
                self.assertEqual(metadata["topic"], "t")
                self.assertIn("channel", metadata)

    def test_an_unreadable_paste_creates_nothing(self):
        before = sorted(os.listdir(self._tmp.name))

        response = client.post("/studio/api/production/project", json={
            "raw": "안녕하세요!", "topic": "t",
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(sorted(os.listdir(self._tmp.name)), before)

    def test_an_unknown_source_is_refused(self):
        response = client.post("/studio/api/production/project", json={
            "raw": RAW, "topic": "t", "source": "whatever",
        })

        self.assertEqual(response.status_code, 400)


class TestResolverPicksUpTheCreatedProject(_Case):

    def test_the_recorded_source_wins_over_disk_detection(self):
        script = {"title": "t", "hook": "", "script": "b", "character": "",
                  "scenes": [{"scene": 1, "narration": "n",
                              "image_prompt": "p"}]}

        created = create_from_script(script, "주제", "wellbeing", "manual")

        self.assertEqual(
            resolver.source_from_metadata(created["project_path"]), "manual",
        )
        self.assertEqual(resolver.detect_source(created["project_path"]), "manual")

    def test_the_resolver_uses_the_script_without_calling_step01(self):
        script = {"title": "붙여넣은 대본", "hook": "", "script": "b",
                  "character": "",
                  "scenes": [{"scene": 1, "narration": "n",
                              "image_prompt": "p"}]}

        created = create_from_script(script, "주제", "wellbeing", "import")

        with patch.object(step01_script, "run") as run:
            data = resolver.run("주제", created["project_path"])

        run.assert_not_called()
        self.assertEqual(data["title"], "붙여넣은 대본")

    def test_an_explicit_argument_still_wins_over_the_metadata(self):
        """Resolver는 명시된 source가 있으면 그것을 따른다."""

        script = {"title": "t", "hook": "", "script": "b", "character": "",
                  "scenes": [{"scene": 1, "narration": "n",
                              "image_prompt": "p"}]}
        created = create_from_script(script, "주제", "wellbeing", "import")

        with patch.object(step01_script, "run", return_value={"x": 1}) as run:
            resolver.run("주제", created["project_path"], source="auto")

        run.assert_called_once()


class TestGenerateReusesThePreparedProject(_Case):
    """Generate 경로를 새로 만들지 않는다 - 인자 하나가 늘었을 뿐이다."""

    def test_without_a_project_id_a_new_project_is_created(self):
        """AUTO는 예전과 완전히 같다."""

        with patch.object(factory_service, "create_project") as create, \
             patch.object(factory_service, "run_pipeline",
                          return_value={"title": "t"}):
            create.return_value = {"id": "new", "path": "/p"}
            factory_service.generate_short_video("주제", "wellbeing")

        create.assert_called_once_with("주제", "wellbeing")

    def test_with_a_project_id_no_new_project_is_created(self):
        with patch.object(factory_service, "create_project") as create, \
             patch.object(factory_service, "resolve_project_path",
                          return_value="/existing") as resolve, \
             patch.object(factory_service, "run_pipeline",
                          return_value={"title": "t"}) as pipeline:
            factory_service.generate_short_video(
                "주제", "wellbeing", project_id="20260101_000001",
            )

        create.assert_not_called()
        resolve.assert_called_once_with("20260101_000001")
        self.assertEqual(pipeline.call_args.kwargs["project_path"], "/existing")

    def test_the_job_carries_the_project_id_through(self):
        with patch.object(studio_jobs, "_run") as run:
            with patch("threading.Thread") as thread:
                studio_jobs.start("주제", "wellbeing", "20260101_000001")

        args = thread.call_args.kwargs["args"]
        self.assertEqual(args[3], "20260101_000001")

    def test_the_generate_endpoint_passes_it_on(self):
        with patch.object(studio_jobs, "start", return_value="job") as start:
            client.post("/studio/api/jobs", json={
                "topic": "주제", "channel": "wellbeing",
                "project_id": "20260101_000001",
            })

        start.assert_called_once_with("주제", "wellbeing", "20260101_000001")

    def test_the_endpoint_still_works_without_it(self):
        """기존 호출부는 전혀 영향받지 않는다."""

        with patch.object(studio_jobs, "start", return_value="job") as start:
            response = client.post("/studio/api/jobs", json={"topic": "주제"})

        self.assertEqual(response.status_code, 200)
        start.assert_called_once_with("주제", "wellbeing", None)


class TestTheScreen(unittest.TestCase):

    def test_the_create_button_appears_after_a_successful_import(self):
        page = client.get("/studio").text

        self.assertIn("createFromImport", page)
        self.assertIn("프로젝트 생성", page)

    def test_the_generate_button_carries_the_prepared_project(self):
        page = client.get("/studio").text

        # Sprint139 - 준비된 프로젝트가 있으면 그것으로, 없고 고른
        # Provider가 있으면 새로 만들어 그것으로 간다. 어느 쪽이든
        # 작업은 project_id를 받는다.
        self.assertIn("preparedProjectId", page)
        self.assertIn("let projectId = preparedProjectId", page)
        self.assertIn("project_id: projectId", page)

    def test_there_is_still_only_one_generate_button(self):
        page = client.get("/studio").text

        self.assertEqual(page.count('id="go"'), 1)

    def test_switching_back_to_auto_drops_the_prepared_script(self):
        """Auto는 대본부터 새로 만드는 방식이다. 준비된 것이 남아
        있으면 고른 것과 다르게 돈다."""

        page = client.get("/studio").text

        self.assertIn("preparedProjectId = null", page)


class TestNothingDownstreamChanged(unittest.TestCase):
    """step02 이후 / Metadata / Upload 수정 금지."""

    def test_the_pipeline_still_calls_the_later_steps_the_same_way(self):
        import app.pipeline.pipeline as pipeline

        source = open(pipeline.__file__, encoding="utf-8").read()

        for call in ("step02_asset_resolve.run(", "step03_voice_resolve.run(",
                     "step04_subtitle.run(", "step05_video.run(",
                     "step06_thumbnail.run(", "step07_quality.run(",
                     "metadata_service.generate_publish_package(",
                     "studio_upload.run_upload_quietly("):
            with self.subTest(call=call):
                self.assertIn(call, source)

    def test_step01_is_still_untouched(self):
        tree = ast.parse(open(step01_script.__file__, encoding="utf-8").read())

        run = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )

        self.assertEqual(
            [n for n in ast.walk(run) if isinstance(n, ast.If)], [],
        )

    def test_create_project_was_not_modified(self):
        """붙여넣기 하나 때문에 모든 프로젝트가 쓰는 함수의 시그니처를
        바꾸지 않는다 - 출처는 만들고 나서 따로 적는다."""

        import inspect

        signature = inspect.signature(project_service.create_project)

        self.assertEqual(list(signature.parameters), ["topic", "channel"])


if __name__ == "__main__":
    unittest.main()
