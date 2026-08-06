"""
Sprint99 - Storage Provider 조립 (Epic 51).

원본(OneDrive)의 storage_provider_factory는 Qt 데스크톱 설정 모델을
입력으로 받는다. 이 저장소에는 Qt가 없으므로 입력만 환경변수로 바꿨고,
판정 규칙은 그대로다 - local/nas면 Local, 그 외에는 S3.

여기서 지킬 것이 하나 더 있다. S3를 쓰지 않는 실행에서는 boto3가
로드되면 안 된다 - 파이프라인이 Upload Core를 안 끌고 오게 한 것과
같은 이유다.
"""

import ast
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.storage import storage_factory
from app.providers.storage.asset_publisher import AssetPublisher
from app.providers.storage.local_storage_provider import LocalStorageProvider
from app.providers.storage.storage_provider import StorageProvider


class TestTheDecisionRuleMatchesTheOriginal(unittest.TestCase):

    def test_the_default_is_local(self):
        """이 저장소에는 공개 호스팅 인프라가 아직 없다. 기본값이
        그 사실을 반영한다."""

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STORAGE_PROVIDER", None)
            self.assertEqual(storage_factory.provider_type(), "local")
            self.assertIsInstance(
                storage_factory.build_storage_provider(), LocalStorageProvider,
            )

    def test_local_and_nas_both_mean_local(self):
        """원본의 판정 규칙 그대로다."""

        for value in ("local", "nas", "LOCAL", " nas "):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"STORAGE_PROVIDER": value}):
                    self.assertIsInstance(
                        storage_factory.build_storage_provider(),
                        LocalStorageProvider,
                    )

    def test_anything_else_builds_the_s3_provider(self):
        with patch.dict(os.environ, {
            "STORAGE_PROVIDER": "s3",
            "STORAGE_S3_ENDPOINT_URL": "https://example.r2.cloudflarestorage.com",
            "STORAGE_S3_BUCKET": "bucket",
            "STORAGE_S3_REGION": "auto",
            "STORAGE_S3_ACCESS_KEY": "key",
            "STORAGE_S3_SECRET_KEY": "secret",
            "STORAGE_S3_PUBLIC_BASE_URL": "https://pub-x.r2.dev",
        }):
            provider = storage_factory.build_storage_provider()

        from app.providers.storage.s3_compatible_storage_provider import (
            S3CompatibleStorageProvider,
        )

        self.assertIsInstance(provider, S3CompatibleStorageProvider)
        self.assertIsInstance(provider, StorageProvider)

    def test_an_explicit_argument_wins_over_the_environment(self):
        with patch.dict(os.environ, {"STORAGE_PROVIDER": "s3"}):
            self.assertIsInstance(
                storage_factory.build_storage_provider("local"),
                LocalStorageProvider,
            )


class TestTheConfigComesFromTheEnvironment(unittest.TestCase):

    def test_the_six_values_are_carried_into_the_provider(self):
        with patch.dict(os.environ, {
            "STORAGE_PROVIDER": "s3",
            "STORAGE_S3_ENDPOINT_URL": "https://endpoint",
            "STORAGE_S3_BUCKET": "my-bucket",
            "STORAGE_S3_REGION": "auto",
            "STORAGE_S3_ACCESS_KEY": "ak",
            "STORAGE_S3_SECRET_KEY": "sk",
            "STORAGE_S3_PUBLIC_BASE_URL": "https://pub-x.r2.dev",
        }):
            provider = storage_factory.build_storage_provider()

        self.assertEqual(provider.config.bucket, "my-bucket")
        self.assertEqual(provider.config.public_base_url, "https://pub-x.r2.dev")

    def test_the_public_url_shape_matches_the_one_real_upload(self):
        """실제로 성공한 단 한 건(2026-08-02, Instagram media
        18144038446551802)이 쓴 URL이 이 모양이었다.

            https://pub-45dd...r2.dev/{uuid4hex}_final_short.mp4

        서명 URL이 아니라 base + key 결합이다.

        endpoint_url을 반드시 준다 - S3CompatibleStorageProvider는
        생성자에서 boto3 클라이언트를 만들기 때문에 비어 있으면
        거기서 실패한다(설정이 덜 된 상태로 조용히 살아 있지 않는다)."""

        with patch.dict(os.environ, {
            "STORAGE_PROVIDER": "s3",
            "STORAGE_S3_ENDPOINT_URL": "https://example.r2.cloudflarestorage.com",
            "STORAGE_S3_PUBLIC_BASE_URL": "https://pub-x.r2.dev/",
            "STORAGE_S3_BUCKET": "b",
        }):
            provider = storage_factory.build_storage_provider()

        self.assertEqual(
            provider.public_url("abc123_final_short.mp4"),
            "https://pub-x.r2.dev/abc123_final_short.mp4",
        )


class TestTheAssetPublisherIsAssembled(unittest.TestCase):

    def test_it_returns_a_publisher_backed_by_the_configured_provider(self):
        with patch.dict(os.environ, {"STORAGE_PROVIDER": "local"}):
            publisher = storage_factory.build_asset_publisher()

        self.assertIsInstance(publisher, AssetPublisher)
        self.assertIsInstance(publisher.storage_provider, LocalStorageProvider)

    def test_a_local_publisher_reports_no_public_url_instead_of_inventing_one(self):
        """없는 URL을 지어내지 않는다 - "공개 URL이 없다"는 사실
        자체가 호출자에게 유효한 정보다."""

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "final_short.mp4")
            with open(path, "wb") as f:
                f.write(b"mp4")

            with patch.dict(os.environ, {"STORAGE_PROVIDER": "local"}):
                asset = storage_factory.build_asset_publisher().publish(path)

        self.assertEqual(asset.public_url, "")
        self.assertEqual(asset.local_path, path)
        self.assertEqual(asset.file_size, 3)


class TestBoto3IsNotLoadedUnlessNeeded(unittest.TestCase):
    """S3를 쓰지 않는 실행에서 boto3가 딸려 오면 안 된다."""

    def test_the_factory_does_not_import_boto3_at_module_level(self):
        tree = ast.parse(open(storage_factory.__file__, encoding="utf-8").read())

        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                top_level.add(node.module or "")

        for name in top_level:
            with self.subTest(imported=name):
                self.assertNotIn("boto", name)
                self.assertNotIn("s3_compatible", name)

    def test_building_a_local_provider_leaves_boto3_unloaded(self):
        code = (
            "import sys\n"
            "from app.providers.storage import storage_factory\n"
            "storage_factory.build_storage_provider('local')\n"
            "print(len([m for m in sys.modules if m.startswith('boto')]))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertEqual(result.stdout.strip(), "0")


class TestNoQtCameAcross(unittest.TestCase):

    def test_the_storage_package_imports_no_desktop_layer(self):
        import pathlib

        base = pathlib.Path(storage_factory.__file__).parent

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

    def test_the_qt_settings_model_was_not_ported(self):
        models = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "models", "desktop_settings.py",
        )

        self.assertFalse(os.path.exists(models))


class TestNothingElseWasTouched(unittest.TestCase):
    """Acceptance - Video Engine / YouTube / OAuth / Pipeline 영향 0."""

    def _imports(self, module):
        tree = ast.parse(open(module.__file__, encoding="utf-8").read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        return names

    def test_the_pipeline_does_not_import_storage(self):
        import app.pipeline.pipeline as pipeline

        for name in self._imports(pipeline):
            with self.subTest(imported=name):
                self.assertNotIn("providers.storage", name)

    def test_the_youtube_upload_step_does_not_import_storage(self):
        """YouTube는 로컬 파일 경로를 그대로 쓴다 - 공개 URL이 필요
        없다(capabilities.requires_public_url=False)."""

        from app.services import youtube_upload_step_service

        for name in self._imports(youtube_upload_step_service):
            with self.subTest(imported=name):
                self.assertNotIn("providers.storage", name)

    def test_the_instagram_runtime_is_not_wired_to_storage_yet(self):
        """이번 스프린트는 Storage 계층만 옮긴다 - 연결은 다음이다."""

        from app.services import real_instagram_runtime

        for name in self._imports(real_instagram_runtime):
            with self.subTest(imported=name):
                self.assertNotIn("providers.storage", name)

    def test_no_storage_endpoint_exists(self):
        from app.main import app

        for path in app.openapi()["paths"]:
            with self.subTest(path=path):
                self.assertNotIn("storage", path.lower())


if __name__ == "__main__":
    unittest.main()
