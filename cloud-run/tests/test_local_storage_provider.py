"""
EPIC AssetPublisher (Production Infrastructure) (RED->GREEN) -
desktop/application/assets/local_storage_provider.py.

실제 업로드를 하지 않는다(Network 호출 없음) - key는 원본 local_path
그대로 돌려준다. public_url()은 항상 빈 문자열이다(로컬 파일 시스템은
공개 URL을 만들 수 없다 - 이게 이 Epic 전체가 존재하는 이유다).
delete()는 실제로 파일을 지우지 않는다 - 이 Provider가 관리하는
사본이 아니라 사용자의 원본 렌더링 결과물이기 때문이다.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.storage.local_storage_provider import LocalStorageProvider
from app.providers.storage.storage_provider import StorageProvider


class TestLocalStorageProviderIsAStorageProvider(unittest.TestCase):

    def test_is_a_storage_provider_subclass(self):
        self.assertTrue(issubclass(LocalStorageProvider, StorageProvider))


class TestLocalStorageProviderUpload(unittest.TestCase):

    def test_upload_returns_the_local_path_as_key(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            provider = LocalStorageProvider()
            key = provider.upload(path)

        self.assertEqual(key, path)

    def test_upload_missing_file_raises_file_not_found(self):
        provider = LocalStorageProvider()
        with self.assertRaises(FileNotFoundError):
            provider.upload("/no/such/file.mp4")

    def test_upload_never_makes_network_calls(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            provider = LocalStorageProvider()
            with patch("socket.socket.connect", side_effect=AssertionError("network used")):
                provider.upload(path)


class TestLocalStorageProviderExistsAndDelete(unittest.TestCase):

    def test_exists_reflects_real_filesystem(self):
        provider = LocalStorageProvider()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            self.assertFalse(provider.exists(path))
            with open(path, "wb") as f:
                f.write(b"data")
            self.assertTrue(provider.exists(path))

    def test_delete_does_not_remove_the_original_file(self):
        provider = LocalStorageProvider()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            provider.delete(path)

            self.assertTrue(os.path.exists(path))


class TestLocalStorageProviderPublicUrl(unittest.TestCase):

    def test_public_url_is_always_empty(self):
        provider = LocalStorageProvider()
        self.assertEqual(provider.public_url("/any/path.mp4"), "")


class TestLocalStorageProviderHealth(unittest.TestCase):

    def test_health_is_always_available(self):
        provider = LocalStorageProvider()
        health = provider.health()
        self.assertTrue(health.available)


if __name__ == "__main__":
    unittest.main()
