"""
EPIC AssetPublisher (Production Infrastructure) (RED->GREEN) -
desktop/application/assets/mock_storage_provider.py.

테스트 전용 - 실제 프로덕션 기본 경로(build_default_adapter_registry()
등)에서는 조립되지 않는다(desktop.application.publishing.connectors.
mock_connector.MockConnector와 동일한 관례). 공개 URL을 자유롭게
설정할 수 있어 "Instagram이 실제로 public_url을 받으면 성공한다"는
경로를 Network 없이 검증할 수 있게 해 준다.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.storage.mock_storage_provider import MockStorageProvider
from app.providers.storage.storage_provider import StorageProvider


class TestMockStorageProviderIsAStorageProvider(unittest.TestCase):

    def test_is_a_storage_provider_subclass(self):
        self.assertTrue(issubclass(MockStorageProvider, StorageProvider))


class TestMockStorageProviderUploadAndUrl(unittest.TestCase):

    def test_upload_then_public_url_returns_configured_template(self):
        provider = MockStorageProvider()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "video.mp4")
            with open(path, "wb") as f:
                f.write(b"data")

            key = provider.upload(path)
            url = provider.public_url(key)

        self.assertTrue(url.startswith("https://mock.storage.local/"))
        self.assertIn(key, url)

    def test_custom_url_template_is_honored(self):
        provider = MockStorageProvider(public_url_template="https://cdn.example.com/{key}")
        key = provider.upload(__file__)

        self.assertEqual(provider.public_url(key), f"https://cdn.example.com/{key}")

    def test_exists_reflects_uploaded_keys(self):
        provider = MockStorageProvider()
        key = provider.upload(__file__)

        self.assertTrue(provider.exists(key))
        self.assertFalse(provider.exists("never-uploaded"))

    def test_delete_removes_from_exists(self):
        provider = MockStorageProvider()
        key = provider.upload(__file__)

        provider.delete(key)

        self.assertFalse(provider.exists(key))


class TestMockStorageProviderFailureMode(unittest.TestCase):

    def test_should_fail_makes_upload_raise(self):
        provider = MockStorageProvider(should_fail=True)

        with self.assertRaises(Exception):
            provider.upload(__file__)

    def test_should_fail_reflected_in_health(self):
        provider = MockStorageProvider(should_fail=True)

        health = provider.health()

        self.assertFalse(health.available)


class TestMockStorageProviderNeverMakesNetworkCalls(unittest.TestCase):

    def test_no_network_calls(self):
        from unittest.mock import patch

        provider = MockStorageProvider()
        with patch("socket.socket.connect", side_effect=AssertionError("network used")):
            key = provider.upload(__file__)
            provider.public_url(key)
            provider.exists(key)
            provider.health()


if __name__ == "__main__":
    unittest.main()
