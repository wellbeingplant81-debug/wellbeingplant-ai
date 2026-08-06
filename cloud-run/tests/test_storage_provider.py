"""
EPIC AssetPublisher (Production Infrastructure) (RED->GREEN) -
desktop/application/assets/storage_provider.py.

StorageProvider는 5개 메서드(upload/delete/exists/public_url/health)만
가진 순수 인터페이스다 - 어떤 구체 저장소도 알지 못한다. 이 계층의
목적은 "AWS S3/Cloudflare R2/GCS/Azure/NAS/사내 파일 서버 어느 것이든
Provider만 추가하면 되도록" 하는 것 - 인터페이스 자체는 플랫폼
독립적이어야 한다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.storage.storage_provider import StorageHealth, StorageProvider


class TestStorageProviderIsAnABC(unittest.TestCase):

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            StorageProvider()

    def test_incomplete_subclass_cannot_instantiate(self):
        class _Incomplete(StorageProvider):
            def upload(self, local_path):
                pass
            # delete/exists/public_url/health가 빠져 있다.

        with self.assertRaises(TypeError):
            _Incomplete()

    def test_full_subclass_can_be_instantiated(self):
        class _Full(StorageProvider):
            def upload(self, local_path):
                return "key"

            def delete(self, key):
                pass

            def exists(self, key):
                return False

            def public_url(self, key):
                return ""

            def health(self):
                return StorageHealth(available=True)

        self.assertIsInstance(_Full(), StorageProvider)


class TestStorageHealth(unittest.TestCase):

    def test_default_message_is_empty(self):
        health = StorageHealth(available=True)
        self.assertEqual(health.message, "")

    def test_available_and_message_are_stored(self):
        health = StorageHealth(available=False, message="연결 실패")
        self.assertFalse(health.available)
        self.assertEqual(health.message, "연결 실패")


if __name__ == "__main__":
    unittest.main()
