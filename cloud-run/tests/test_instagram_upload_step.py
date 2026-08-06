"""
Sprint101 - Instagram Upload Step (Epic 53).

Sprint97(Runtime) / Sprint99(Storage) / Sprint100(Adapter)를 엮는 층이다.
업로드 로직은 여기에 없다 - 게시 순서와 재시도는 Adapter가 이미 갖고
있고, 이 파일은 판정과 조립과 기록만 한다.

판정 순서가 곧 안전장치다. 플래그 -> Meta 자격증명 -> 로그인 상태.
앞에서 막히면 뒤쪽은 실행되지 않는다. 특히 브라우저를 여는
runtime.login()까지 가지 않아야 한다(Sprint90/91에서 YouTube에 같은
함정이 있었다).
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
from app.services import instagram_upload_step_service as step
from app.services import oauth_health
from app.services.publishing.connector_result import ConnectorResult


class _Adapter:
    """RuntimeBackedPublishAdapter 자리. 실제 네트워크는 없다."""

    def __init__(self, result=None):
        self.result = result or ConnectorResult(
            status="Published", platform="Instagram",
            external_id="media-1", permalink="https://instagr.am/p/x",
            storage_url="https://pub-x.r2.dev/abc_final_short.mp4",
        )
        self.plans = []

    def submit(self, plan):
        self.plans.append(plan)
        return self.result


def _health(status):
    return oauth_health.CredentialHealth(status, "msg", 0.0)


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = os.path.join(self._tmp.name, "20260101_000001")
        os.makedirs(os.path.join(self.project, "video"))
        with open(os.path.join(self.project, "video", "final_short.mp4"), "wb") as f:
            f.write(b"mp4")

        self.credentials = {
            "INSTAGRAM_OAUTH_CLIENT_ID": "id",
            "INSTAGRAM_OAUTH_CLIENT_SECRET": "secret",
            "INSTAGRAM_OAUTH_TOKEN_STORE_PATH": os.path.join(
                self._tmp.name, "tokens.json"),
        }

    def _data(self):
        return {"title": "대본 제목", "script": "대본 본문", "hashtags": ["#대본"]}

    def _package(self, **extra):
        payload = {"title": "패키지 제목", "description": "패키지 설명",
                   "hashtags": ["#혈관", "#건강"]}
        payload.update(extra)
        with open(os.path.join(self.project, "publish_package.json"),
                  "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def _run(self, adapter=None, health=oauth_health.READY, env=None,
             enabled=True):
        environ = dict(self.credentials)
        environ.update(env or {})

        with patch.object(config, "ENABLE_INSTAGRAM_UPLOAD", enabled), \
             patch.dict(os.environ, environ), \
             patch.object(step, "_check_health", lambda: _health(health)):
            return step.run_instagram_upload_step(
                "혈관 건강", self.project, self._data(), adapter=adapter,
            )


class TestTheGateOrder(_Case):
    """앞 관문에서 막히면 뒤쪽 코드는 실행되지 않는다."""

    def test_the_flag_is_off_by_default(self):
        self.assertFalse(config.ENABLE_INSTAGRAM_UPLOAD)

    def test_a_disabled_flag_refuses_before_anything_else(self):
        adapter = _Adapter()

        with patch.object(config, "ENABLE_INSTAGRAM_UPLOAD", False):
            result = step.run_instagram_upload_step(
                "혈관", self.project, self._data(), adapter=adapter,
            )

        self.assertEqual(result["outcome"], "skipped")
        self.assertIn("ENABLE_INSTAGRAM_UPLOAD", result["error"])
        self.assertEqual(adapter.plans, [])

    def test_missing_meta_credentials_refuse_before_the_health_check(self):
        adapter = _Adapter()
        checked = []

        with patch.object(config, "ENABLE_INSTAGRAM_UPLOAD", True), \
             patch.dict(os.environ, {"INSTAGRAM_OAUTH_CLIENT_ID": "",
                                     "INSTAGRAM_OAUTH_CLIENT_SECRET": ""}), \
             patch.object(step, "_check_health",
                          lambda: checked.append(1) or _health("READY")):
            result = step.run_instagram_upload_step(
                "혈관", self.project, self._data(), adapter=adapter,
            )

        self.assertEqual(result["outcome"], "skipped")
        self.assertIn("Meta App 자격증명", result["error"])
        self.assertEqual(checked, [])
        self.assertEqual(adapter.plans, [])

    def test_no_stored_login_refuses_before_the_adapter(self):
        """Adapter가 부르는 runtime.login()은 브라우저를 연다."""

        adapter = _Adapter()

        result = self._run(adapter, health=oauth_health.REAUTH_REQUIRED)

        self.assertEqual(result["outcome"], "skipped")
        self.assertIn("로그인", result["error"])
        self.assertEqual(adapter.plans, [])

    def test_an_expired_token_is_allowed_because_refresh_needs_no_browser(self):
        adapter = _Adapter()

        result = self._run(adapter, health=oauth_health.EXPIRED)

        self.assertTrue(result["success"])
        self.assertEqual(len(adapter.plans), 1)

    def test_the_step_never_calls_authenticate_itself(self):
        called = set()
        tree = ast.parse(open(step.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Attribute):
                    called.add(target.attr)
                elif isinstance(target, ast.Name):
                    called.add(target.id)

        self.assertNotIn("authenticate", called)
        self.assertNotIn("login", called)


class TestThePlanIsBuiltFromArtifacts(_Case):

    def test_the_publish_package_is_preferred(self):
        """Sprint93이 만든 자리다 - YouTube 업로드도 같은 곳을 읽는다."""

        self._package()
        adapter = _Adapter()

        self._run(adapter)

        plan = adapter.plans[0]
        self.assertEqual(plan.title, "패키지 제목")
        self.assertEqual(plan.description, "패키지 설명")
        self.assertEqual(plan.hashtags, ["#혈관", "#건강"])

    def test_without_a_package_the_script_is_used(self):
        adapter = _Adapter()

        self._run(adapter)

        plan = adapter.plans[0]
        self.assertEqual(plan.title, "대본 제목")
        self.assertEqual(plan.description, "대본 본문")

    def test_the_platform_and_output_folder_are_set(self):
        adapter = _Adapter()

        self._run(adapter)

        plan = adapter.plans[0]
        self.assertEqual(plan.platform, "Instagram")
        self.assertEqual(plan.output_folder, self.project)
        self.assertEqual(plan.job_id, "20260101_000001")

    def test_tags_are_accepted_when_hashtags_are_absent(self):
        self._package(hashtags=[], tags=["혈관", "건강"])
        adapter = _Adapter()

        self._run(adapter)

        self.assertEqual(adapter.plans[0].hashtags, ["혈관", "건강"])

    def test_a_corrupt_package_falls_back_instead_of_crashing(self):
        with open(os.path.join(self.project, "publish_package.json"),
                  "w", encoding="utf-8") as f:
            f.write("{ broken")
        adapter = _Adapter()

        self._run(adapter)

        self.assertEqual(adapter.plans[0].title, "대본 제목")

    def test_the_caller_data_is_not_mutated(self):
        data = self._data()
        before = json.dumps(data, ensure_ascii=False, sort_keys=True)

        step.build_plan("주제", self.project, data)

        self.assertEqual(
            json.dumps(data, ensure_ascii=False, sort_keys=True), before,
        )


class TestTheResultIsRecorded(_Case):

    def test_a_success_is_written_with_the_permalink(self):
        result = self._run(_Adapter())

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "uploaded")
        self.assertEqual(result["upload_id"], "media-1")
        self.assertEqual(result["url"], "https://instagr.am/p/x")
        self.assertEqual(
            result["storage_url"], "https://pub-x.r2.dev/abc_final_short.mp4",
        )

    def test_the_result_file_lands_next_to_the_project(self):
        self._run(_Adapter())

        path = os.path.join(self.project, step.RESULT_FILENAME)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(step.read_result(self.project)["upload_id"], "media-1")

    def test_it_does_not_collide_with_the_youtube_result(self):
        from app.services import studio_upload

        self.assertNotEqual(step.RESULT_FILENAME, studio_upload.RESULT_FILENAME)

    def test_a_failure_is_recorded_with_its_category(self):
        adapter = _Adapter(ConnectorResult(
            status="Failed", platform="Instagram",
            message="공개 URL이 없습니다", retryable=False,
            error_category="",
        ))

        result = self._run(adapter)

        self.assertFalse(result["success"])
        self.assertEqual(result["outcome"], "failed")
        self.assertIn("공개 URL", result["error"])
        self.assertFalse(result["retryable"])

    def test_a_rate_limit_failure_carries_its_category(self):
        adapter = _Adapter(ConnectorResult(
            status="Failed", platform="Instagram", message="429",
            retryable=True, error_category="RATE_LIMIT",
        ))

        result = self._run(adapter)

        self.assertEqual(result["error_category"], "RATE_LIMIT")
        self.assertTrue(result["retryable"])

    def test_refusals_are_recorded_too(self):
        with patch.object(config, "ENABLE_INSTAGRAM_UPLOAD", False):
            step.run_instagram_upload_step("t", self.project, self._data())

        self.assertFalse(step.read_result(self.project)["success"])

    def test_production_artifacts_are_not_touched(self):
        video = os.path.join(self.project, "video", "final_short.mp4")
        before = os.path.getsize(video)

        self._run(_Adapter())

        self.assertEqual(os.path.getsize(video), before)


class TestNothingWasReimplemented(unittest.TestCase):
    """"새 Upload/Publish/Retry 구현 금지"."""

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_it_uses_the_adapter_rather_than_the_runtime_directly(self):
        names = self._imports(step)

        self.assertTrue(any("instagram_adapter" in n for n in names))
        self.assertFalse(any("real_instagram_runtime" in n for n in names))

    def test_it_contains_no_retry_or_polling_logic(self):
        source = open(step.__file__, encoding="utf-8").read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.While, ast.Try)):
                # _load()의 try/except 하나만 허용된다(JSON 읽기).
                continue
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                with self.subTest(call=node.func.attr):
                    self.assertNotEqual(node.func.attr, "sleep")

    def test_heavy_layers_are_imported_lazily(self):
        """플래그가 꺼져 있으면 Adapter도 boto3도 들이지 않는다."""

        tree = ast.parse(open(step.__file__, encoding="utf-8").read())

        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                top_level.add(node.module or "")
            elif isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)

        for forbidden in ("storage_factory", "instagram_adapter", "boto3"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in n for n in top_level), forbidden,
                )

    def test_importing_the_step_does_not_load_boto3(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, "-c",
             "import sys\n"
             "from app.services import instagram_upload_step_service\n"
             "print(len([m for m in sys.modules if m.startswith('boto')]))\n"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertEqual(result.stdout.strip(), "0")


class TestNothingElseWasTouched(unittest.TestCase):
    """Acceptance - Video Engine / YouTube / Storage / OAuth 영향 0."""

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_the_youtube_step_does_not_know_about_instagram(self):
        from app.services import youtube_upload_step_service

        for name in self._imports(youtube_upload_step_service):
            with self.subTest(imported=name):
                self.assertNotIn("instagram", name.lower())

    def test_the_pipeline_does_not_import_the_instagram_step(self):
        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("instagram", name.lower())

    def test_studio_upload_still_only_runs_youtube(self):
        """Queue/Workflow 연결은 이번 범위가 아니다."""

        from app.services import studio_upload

        for name in self._imports(studio_upload):
            with self.subTest(imported=name):
                self.assertNotIn("instagram", name.lower())

    def test_no_instagram_endpoint_exists(self):
        from app.main import app

        for path in app.openapi()["paths"]:
            with self.subTest(path=path):
                self.assertNotIn("instagram", path.lower())


if __name__ == "__main__":
    unittest.main()
