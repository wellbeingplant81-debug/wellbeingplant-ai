"""
EPIC Instagram Connector (Production) -
desktop/application/assets/asset_publisher.py.
EPIC AssetPublisher (Production Infrastructure) (RED->GREEN) -
desktop/application/assets/storage_asset_publisher.py.

AssetPublisher는 "Local File -> Public Asset -> AssetReference"라는
플랫폼 공통 계약 하나(publish())만 갖는다. StorageAssetPublisher는
이 Epic이 만든 유일한 구현체다(과거 이름 LocalPathAssetPublisher를
대체 - StorageProvider를 DI로 주입받는 지금 구조에서는 "Local 전용"
이라는 이름이 더 이상 정확하지 않다, 외부 참조는 이 테스트 파일뿐이라
이름 변경의 위험이 낮다고 판단했다).

StorageAssetPublisher 자신은 어떤 저장소를 쓸지 직접 고르지 않는다 -
StorageProvider를 생성자로 주입받을 뿐이다("AssetPublisher는 Storage
Provider를 직접 선택하지 않는다. DI로 받는다"). 기본값(인자를 안 주면)
은 LocalStorageProvider() - 실제 공개 호스팅은 하지 않는다(Network
호출 없음, 그런 인프라가 아직 없다는 것을 지어내지 않는다) - 기존
LocalPathAssetPublisher와 100% 동일한 관측 가능한 동작을 유지한다.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.storage.asset_publisher import AssetPublisher
from app.providers.storage.asset_reference import AssetReference
from app.providers.storage.local_storage_provider import LocalStorageProvider
from app.providers.storage.mock_storage_provider import MockStorageProvider
from app.providers.storage.storage_asset_publisher import StorageAssetPublisher


class TestAssetPublisherIsAnABC(unittest.TestCase):

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            AssetPublisher()

    def test_storage_asset_publisher_is_a_subclass(self):
        self.assertTrue(issubclass(StorageAssetPublisher, AssetPublisher))


class TestStorageAssetPublisherDefaultsToLocalStorage(unittest.TestCase):
    """생성자 인자 없이 쓰면 기존 LocalPathAssetPublisher와 관측 가능한
    동작이 100% 동일해야 한다(Regression Zero)."""

    def test_publish_existing_file_fills_local_path_mime_and_size(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"0" * 1024)

            publisher = StorageAssetPublisher()
            reference = publisher.publish(path)

        self.assertIsInstance(reference, AssetReference)
        self.assertEqual(reference.local_path, path)
        self.assertEqual(reference.mime_type, "video/mp4")
        self.assertEqual(reference.file_size, 1024)
        self.assertEqual(reference.public_url, "")  # LocalStorageProvider는 공개 URL이 없다.

    def test_default_storage_provider_is_local(self):
        publisher = StorageAssetPublisher()
        self.assertIsInstance(publisher.storage_provider, LocalStorageProvider)

    def test_publish_never_makes_network_calls_by_default(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"x")

            publisher = StorageAssetPublisher()
            with patch("socket.socket.connect", side_effect=AssertionError("network used")):
                publisher.publish(path)

    def test_publish_missing_file_raises_file_not_found(self):
        publisher = StorageAssetPublisher()

        with self.assertRaises(FileNotFoundError):
            publisher.publish("/no/such/file.mp4")

    def test_publish_missing_file_message_is_human_readable(self):
        """Phase 7, Sprint 3 - 기존에는 FileNotFoundError(local_path)로
        경로 문자열 자체만 메시지였다("찾을 수 없습니다" 같은 설명이
        없어 Operations Center 화면에 경로만 덩그러니 표시됐다). 사람이
        읽고 바로 원인을 알 수 있는 문장이어야 한다 - 경로 자체는
        그대로 메시지 안에 포함되어야 한다(정보 손실 없음)."""
        publisher = StorageAssetPublisher()

        with self.assertRaises(FileNotFoundError) as ctx:
            publisher.publish("/no/such/file.mp4")

        message = str(ctx.exception)
        self.assertIn("찾을 수 없습니다", message)
        self.assertIn("/no/such/file.mp4", message)


class TestStorageAssetPublisherUsesInjectedProvider(unittest.TestCase):
    """핵심 요구사항 - "StorageProvider를 직접 선택하지 않는다. DI로
    받는다". 주입된 Provider가 실제 public_url을 돌려주면 그대로
    AssetReference에 반영돼야 한다."""

    def test_injected_provider_supplies_public_url(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            mock_storage = MockStorageProvider(
                public_url_template="https://cdn.example.com/{key}",
            )
            publisher = StorageAssetPublisher(storage_provider=mock_storage)
            reference = publisher.publish(path)

        self.assertEqual(reference.public_url, "https://cdn.example.com/video.mp4")
        self.assertEqual(reference.local_path, path)

    def test_upload_is_delegated_to_the_injected_provider(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            mock_storage = MockStorageProvider()
            publisher = StorageAssetPublisher(storage_provider=mock_storage)
            publisher.publish(path)

        self.assertTrue(mock_storage.exists("video.mp4"))

    def test_provider_upload_failure_propagates(self):
        mock_storage = MockStorageProvider(should_fail=True)
        publisher = StorageAssetPublisher(storage_provider=mock_storage)

        with self.assertRaises(Exception):
            publisher.publish(__file__)


class TestStorageAssetPublisherWithS3CompatibleProvider(unittest.TestCase):
    """EPIC S3-Compatible Storage Provider (Production) - 핵심 요구사항
    "AssetPublisher는 S3인지 R2인지 MinIO인지 몰라야 한다"를 직접
    증명한다. StorageAssetPublisher 코드는 한 줄도 안 바뀌었다 - 그저
    다른 StorageProvider 구현체를 주입받았을 뿐이다."""

    def test_publish_with_real_s3_compatible_provider_class_yields_public_url(self):
        from app.providers.storage.s3_compatible_storage_config import (
            S3CompatibleStorageConfig,
        )
        from app.providers.storage.s3_compatible_storage_provider import (
            S3CompatibleStorageProvider,
        )

        class _FakeS3Client:
            def upload_file(self, Filename, Bucket, Key):
                pass

        config = S3CompatibleStorageConfig(
            endpoint_url="https://account.r2.cloudflarestorage.com",
            bucket="assets", region="auto", access_key="ak", secret_key="sk",
            public_base_url="https://cdn.example.com",
        )
        s3_provider = S3CompatibleStorageProvider(config, client=_FakeS3Client())
        publisher = StorageAssetPublisher(storage_provider=s3_provider)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            reference = publisher.publish(path)

        self.assertTrue(reference.public_url.startswith("https://cdn.example.com/"))
        self.assertTrue(reference.public_url.endswith("_video.mp4"))
        self.assertEqual(reference.local_path, path)
        self.assertEqual(reference.mime_type, "video/mp4")


if __name__ == "__main__":
    unittest.main()
