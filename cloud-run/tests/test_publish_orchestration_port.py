"""
Sprint100 - Publish Orchestration 이식 (Epic 52).

Sprint97이 Instagram Runtime을, Sprint99가 Storage 계층을 가져왔다.
그 둘을 실제로 엮어 게시 순서를 지휘하는 것이 여기다 - 공개 URL 준비,
2단계 게시(Container -> 폴링 -> Publish), 일시적 오류 재시도, Dry Run.

전부 이식이다. 새 Publish/Retry/Polling 구현을 만들지 않았다.

아직 아무도 부르지 않는다. Adapter가 조립되고 Runtime과 연결된
상태까지가 이번 범위다.
"""

import ast
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.services.publishing import runtime_backed_publish_adapter as rbpa
from app.services.publishing.connector_result import ConnectorResult
from app.services.publishing.instagram_adapter import InstagramAdapter
from app.services.publishing.publish_platform import PublishPlatform
from app.services.publishing.publishing_connector import PublishingConnector
from app.services.publishing.publishing_plan_model import PublishingPlan
from app.services.publishing.runtime_backed_publish_adapter import (
    RuntimeBackedPublishAdapter,
    resolve_thumbnail_path,
    resolve_video_path,
)
from app.services.publishing_runtime_protocol import (
    PublishingRuntimeProtocol,
    RuntimeCapabilities,
    TransientRuntimeError,
)


class _Runtime(PublishingRuntimeProtocol):
    """네트워크 없는 Runtime. 실제 Meta/Google을 부르지 않는다."""

    def __init__(self, caps=None, fail_times=0):
        self.capabilities = caps or RuntimeCapabilities(
            two_phase_publish=True, requires_public_url=True,
            supports_permalink=True,
        )
        self.calls = []
        self.statuses = ["FINISHED"]
        self._fail_times = fail_times

    def login(self, account_id):
        self.calls.append(("login", account_id))
        return type("Cred", (), {"account_id": account_id})()

    def refresh_token(self, credential):
        return credential

    def upload_media(self, credential, video_url, caption, cover_url=None, plan=None):
        self.calls.append(("upload_media", video_url, caption, cover_url))
        if self._fail_times > 0:
            self._fail_times -= 1
            raise TransientRuntimeError("일시적 오류")
        return "container-1"

    def publish_media(self, credential, container_id):
        self.calls.append(("publish_media", container_id))
        return "media-1"

    def get_publish_status(self, credential, container_id):
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]

    def revoke(self, credential):
        pass

    def get_permalink(self, credential, media_id):
        return f"https://instagr.am/{media_id}"


class _Publisher:
    def __init__(self, public_url="https://cdn/v.mp4"):
        self.public_url = public_url
        self.published = []

    def publish(self, local_path):
        self.published.append(local_path)
        from app.providers.storage.asset_reference import AssetReference

        return AssetReference(local_path=local_path, public_url=self.public_url)


def _plan(folder="", dry_run=False):
    return PublishingPlan(
        job_id="job-1", platform="Instagram", title="제목",
        description="설명", hashtags=["#건강"],
        output_folder=folder, dry_run=dry_run,
    )


class _Case(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = self._tmp.name
        os.makedirs(os.path.join(self.folder, "video"), exist_ok=True)
        with open(os.path.join(self.folder, "video", "final_short.mp4"), "wb") as f:
            f.write(b"mp4")

    def _adapter(self, runtime=None, publisher=None, **kwargs):
        return RuntimeBackedPublishAdapter(
            platform="Instagram",
            runtime=runtime or _Runtime(),
            asset_publisher=publisher,
            poll_interval_seconds=0,
            **kwargs
        )


class TestTheContractIsPorted(unittest.TestCase):

    def test_the_adapter_is_a_publish_platform(self):
        self.assertTrue(issubclass(RuntimeBackedPublishAdapter, PublishPlatform))
        self.assertTrue(issubclass(PublishPlatform, PublishingConnector))

    def test_capabilities_are_delegated_to_the_runtime(self):
        """Adapter가 플랫폼별 분기를 갖지 않는다 - Runtime이 답한다."""

        adapter = RuntimeBackedPublishAdapter(
            platform="X",
            runtime=_Runtime(RuntimeCapabilities(
                two_phase_publish=True, requires_public_url=True,
                supports_schedule=False, supports_thumbnail=True,
                supports_playlist=False, supports_shorts=True,
            )),
        )

        self.assertFalse(adapter.supports_schedule())
        self.assertTrue(adapter.supports_thumbnail())
        self.assertFalse(adapter.supports_playlist())
        self.assertTrue(adapter.supports_shorts())

    def test_the_instagram_adapter_assembles_the_real_runtime(self):
        adapter = InstagramAdapter()

        self.assertEqual(adapter.platform, "Instagram")
        self.assertEqual(type(adapter._runtime).__name__, "RealInstagramRuntime")

    def test_a_runtime_can_be_injected_instead(self):
        runtime = _Runtime()

        self.assertIs(InstagramAdapter(runtime=runtime)._runtime, runtime)


class TestArtifactPathsComeFromThisEngine(_Case):
    """원본은 render_profile로 shorts/longform 두 이름을 찾아봤다.
    이 엔진은 longform을 만들지 않는다(Sprint91의 그 사실)."""

    def test_the_video_path_matches_what_the_engine_writes(self):
        from app.services.studio_service import MEDIA_KINDS

        self.assertEqual(
            resolve_video_path(self.folder),
            os.path.join(self.folder, *MEDIA_KINDS["video"].split("/")),
        )

    def test_a_missing_thumbnail_is_none_not_a_guess(self):
        self.assertIsNone(resolve_thumbnail_path(self.folder))

    def test_a_present_thumbnail_is_found(self):
        path = os.path.join(self.folder, "thumbnail.png")
        with open(path, "wb") as f:
            f.write(b"png")

        self.assertEqual(resolve_thumbnail_path(self.folder), path)

    def test_an_empty_folder_gives_empty_not_a_crash(self):
        self.assertEqual(resolve_video_path(""), "")
        self.assertIsNone(resolve_thumbnail_path(""))

    def test_no_longform_axis_was_dragged_in(self):
        tree = ast.parse(open(rbpa.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                with self.subTest(imported=name):
                    self.assertNotIn("render_profile", name)


class TestThePublicUrlGate(_Case):
    """Instagram은 공개 URL만 받는다. 그것이 없으면 시도조차 하지
    않는다 - Sprint98 로그에서 97번 나온 실패다."""

    def test_no_asset_publisher_fails_without_calling_the_runtime(self):
        runtime = _Runtime()

        result = self._adapter(runtime, publisher=None).submit(_plan(self.folder))

        self.assertEqual(result.status, "Failed")
        self.assertFalse(result.retryable)
        self.assertEqual(runtime.calls, [])

    def test_an_empty_public_url_fails_and_is_not_retryable(self):
        runtime = _Runtime()

        result = self._adapter(runtime, _Publisher(public_url="")).submit(
            _plan(self.folder),
        )

        self.assertEqual(result.status, "Failed")
        self.assertFalse(result.retryable)
        self.assertIn("공개 URL", result.message)
        self.assertEqual(runtime.calls, [])

    def test_a_missing_local_file_fails_fast(self):
        """다시 시도해도 소용없다 - Retry Queue에 영구히 걸어 두지
        않는다."""

        class _Missing:
            def publish(self, local_path):
                raise FileNotFoundError(f"동영상 파일을 찾을 수 없습니다: {local_path}")

        result = self._adapter(_Runtime(), _Missing()).submit(_plan(self.folder))

        self.assertEqual(result.status, "Failed")
        self.assertFalse(result.retryable)
        self.assertEqual(result.error_category, "FILE_NOT_FOUND")

    def test_the_public_url_is_what_reaches_the_runtime(self):
        runtime = _Runtime()

        self._adapter(runtime, _Publisher("https://pub-x.r2.dev/abc_final_short.mp4")).submit(
            _plan(self.folder),
        )

        upload = [c for c in runtime.calls if c[0] == "upload_media"][0]
        self.assertEqual(upload[1], "https://pub-x.r2.dev/abc_final_short.mp4")


class TestTwoPhasePublish(_Case):

    def test_container_then_poll_then_publish(self):
        runtime = _Runtime()
        runtime.statuses = ["IN_PROGRESS", "FINISHED"]

        result = self._adapter(runtime, _Publisher()).submit(_plan(self.folder))

        names = [c[0] for c in runtime.calls]
        self.assertEqual(names, ["login", "upload_media", "publish_media"])
        self.assertEqual(result.status, "Published")
        self.assertEqual(result.external_id, "media-1")

    def test_a_single_phase_runtime_never_calls_publish_media(self):
        """YouTube류 - upload_media()가 이미 최종 게시다."""

        runtime = _Runtime(RuntimeCapabilities(
            two_phase_publish=False, requires_public_url=False,
        ))

        self._adapter(runtime).submit(_plan(self.folder))

        self.assertNotIn("publish_media", [c[0] for c in runtime.calls])

    def test_a_single_phase_runtime_gets_a_local_path_not_a_url(self):
        runtime = _Runtime(RuntimeCapabilities(
            two_phase_publish=False, requires_public_url=False,
        ))

        self._adapter(runtime).submit(_plan(self.folder))

        upload = [c for c in runtime.calls if c[0] == "upload_media"][0]
        self.assertTrue(upload[1].endswith("final_short.mp4"))
        self.assertFalse(upload[1].startswith("http"))

    def test_the_storage_url_is_only_recorded_when_it_is_really_public(self):
        """공개 URL이 아닌 로컬 경로를 storage_url로 지어내지 않는다."""

        runtime = _Runtime(RuntimeCapabilities(
            two_phase_publish=False, requires_public_url=False,
        ))

        result = self._adapter(runtime).submit(_plan(self.folder))

        self.assertEqual(result.storage_url, "")


class TestTransientRetryIsPorted(_Case):
    """새 Retry를 만들지 않았다 - 원본의 것이 그대로 동작하는지만
    확인한다."""

    def test_a_transient_failure_is_retried_and_can_succeed(self):
        runtime = _Runtime(fail_times=1)

        with patch.object(rbpa.time, "sleep", lambda s: None):
            result = self._adapter(runtime, _Publisher()).submit(_plan(self.folder))

        self.assertEqual(result.status, "Published")
        self.assertEqual(
            len([c for c in runtime.calls if c[0] == "upload_media"]), 2,
        )

    def test_the_retry_budget_is_finite(self):
        runtime = _Runtime(fail_times=99)

        with patch.object(rbpa.time, "sleep", lambda s: None):
            result = self._adapter(runtime, _Publisher()).submit(_plan(self.folder))

        self.assertEqual(result.status, "Failed")
        self.assertTrue(result.retryable)
        self.assertLess(
            len([c for c in runtime.calls if c[0] == "upload_media"]), 10,
        )


class TestDryRun(_Case):

    def test_a_dry_run_never_publishes(self):
        runtime = _Runtime()

        result = self._adapter(runtime, _Publisher()).submit(
            _plan(self.folder, dry_run=True),
        )

        self.assertIn("DryRun", result.status)
        self.assertNotIn("publish_media", [c[0] for c in runtime.calls])


class TestNothingWasInvented(unittest.TestCase):
    """"새 Publish/Retry/Polling/Runtime 구현 금지"."""

    def test_no_qt_or_desktop_layer_came_across(self):
        import pathlib

        base = pathlib.Path(rbpa.__file__).parent

        for path in base.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    with self.subTest(file=path.name, imported=name):
                        self.assertNotIn("desktop", name)
                        self.assertNotIn("PySide", name)

    def test_the_publish_manager_was_not_ported(self):
        """PublishManager는 TikTok/Threads Adapter와 youtube_connector를
        끌고 온다 - 그 셋은 이 저장소에서 금지이거나(TikTok/Threads)
        기존 YouTube 경로와 경쟁한다(youtube_connector)."""

        import pathlib

        base = pathlib.Path(rbpa.__file__).parent

        for name in ("publish_manager.py", "tiktok_adapter.py",
                     "threads_adapter.py", "youtube_adapter.py",
                     "youtube_connector.py", "connector_registry.py"):
            with self.subTest(name=name):
                self.assertFalse((base / name).exists())


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

    def test_the_pipeline_does_not_import_publishing(self):
        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("services.publishing", name)

    def test_the_youtube_upload_step_is_untouched(self):
        from app.services import youtube_upload_step_service

        for name in self._imports(youtube_upload_step_service):
            with self.subTest(imported=name):
                self.assertNotIn("services.publishing", name)

    def test_only_the_instagram_step_uses_the_adapter(self):
        """Sprint100에는 "아직 아무도 부르지 않는다"였다. Sprint101이
        instagram_upload_step_service를 붙였으므로 그 문장은 더 이상
        사실이 아니다.

        지켜야 할 경계는 그대로다 - Adapter를 쓰는 곳은 그 한 곳뿐이고,
        Pipeline/Queue/Workflow/UI는 여전히 모른다.

        원문을 훑지 않는다 - instagram_runtime과 publishing_runtime_
        protocol의 설명 주석이 RuntimeBackedPublishAdapter를 언급한다
        (그 계약을 설명하느라). 실제로 쓰는지는 import가 말한다."""

        import pathlib

        app_root = pathlib.Path(rbpa.__file__).parent.parent.parent
        callers = []

        for path in app_root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            if path.parent.name == "publishing":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                elif isinstance(node, ast.Import):
                    module = " ".join(a.name for a in node.names)
                if "services.publishing." in module:
                    callers.append(path.name)

        # Sprint237 - 형제가 하나 늘었다.
        #
        # tiktok_upload_step_service 는 instagram 쪽과 같은 종류다 -
        # 같은 자리, 같은 판정 순서, 같은 결과 모양. 이 시험의
        # docstring 이 이미 겪은 일이기도 하다(Sprint100 "아무도 부르지
        # 않는다" -> Sprint101 instagram 이 붙음).
        #
        # 지켜야 할 경계는 그대로다. 늘어난 것은 스텝 서비스 한 벌이고,
        # Pipeline/Queue/Workflow/UI 는 여전히 모른다 - 아래 두 시험이
        # 그것을 따로 못 박는다.
        self.assertEqual(
            sorted(set(callers)),
            ["instagram_upload_step_service.py",
             "tiktok_upload_step_service.py"],
        )

    def test_the_worker_does_not_know_the_adapter(self):
        """
        Sprint237 - 일꾼은 줄에서 집어 스텝 서비스를 부를 뿐이다.
        여기서 Adapter 를 알기 시작하면 스텝 서비스와 같은 일을 두
        곳이 하게 된다.
        """

        from app.services import publish_worker

        for name in self._imports(publish_worker):
            with self.subTest(imported=name):
                self.assertNotIn("services.publishing", name)

    def test_the_queue_itself_knows_nothing(self):
        """줄은 무엇을 올릴 차례인지만 안다 - 올리는 법을 모른다."""

        from app.services import publish_queue

        for name in self._imports(publish_queue):
            with self.subTest(imported=name):
                self.assertNotIn("services.publishing", name)
                self.assertNotIn("runtime", name)

    # Sprint235 - 줄 세우는 자리 하나가 생겼다.
    #
    # 전에는 발행에 HTTP 자리가 아예 없었고, 이 시험은 그 사실을
    # 못 박고 있었다. 이제 화면에서 [이 영상 올리기] 를 누르면
    # publish_queue 에 한 줄이 선다 - 그 자리다.
    #
    # 지키려던 뜻은 그대로다. 저 자리는 **올리지 않는다** - 무엇을
    # 올릴 차례인지만 적는다. Adapter 도 Runtime 도 모른다(그 경계는
    # 위의 test_only_the_instagram_step_uses_the_adapter 가 지킨다).
    # 그래서 "자리가 없다" 대신 "이 자리들뿐이고, 그것도 올리지
    # 않는다" 를 재도록 옮긴다.
    QUEUE_ENDPOINTS = {"/studio/api/publish/queue"}

    def test_the_only_publish_endpoints_are_the_queue(self):
        from app.main import app

        found = {path for path in app.openapi()["paths"]
                 if "publish" in path.lower()}

        self.assertEqual(found, self.QUEUE_ENDPOINTS, found)

    def test_the_queue_endpoint_does_not_publish(self):
        """
        줄에 세우는 자리가 어느 날 직접 올리기 시작하면, 같은 일을
        두 곳이 하게 된다 - 이 저장소가 여러 번 겪은 그것이다.
        """

        import app.routers.studio as studio

        source = open(studio.__file__, encoding="utf-8").read()

        at = source.index('@router.post("/api/publish/queue")')
        block = source[at:at + 1600]

        # 설명을 걷어낸다. 무엇을 부르지 않는지 적어 둔 주석이 그
        # 이름을 담게 되고, 그러면 가드가 제 설명에 걸린다 - 이
        # 저장소에서 이미 세 번 겪었다(실제로 여기서도 걸렸다).
        doing = "\n".join(
            line.split("#")[0] for line in block.splitlines()
            if not line.lstrip().startswith("#"))

        for forbidden in ("runtime", "adapter", "requests.", "upload_media"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, doing.lower())


if __name__ == "__main__":
    unittest.main()
