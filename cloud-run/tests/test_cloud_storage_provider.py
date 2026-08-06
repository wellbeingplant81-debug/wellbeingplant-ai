"""
EPIC AssetPublisher (Production Infrastructure) (RED->GREEN) -
desktop/application/assets/cloud_storage_provider.py.

이번 Epic은 AWS/Cloudflare/GCS/Azure 어느 것도 구현하지 않는다 -
CloudStorageProvider는 "실제 클라우드 저장소는 여기서부터 상속받아
만든다"는 자리표시자(추상 클래스)일 뿐이다. StorageProvider의 5개
계약을 그대로 상속받되, 구현체가 하나도 없어 여전히 인스턴스화할 수
없다는 것만 증명한다.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.storage.cloud_storage_provider import CloudStorageProvider
from app.providers.storage.storage_provider import StorageProvider


class TestCloudStorageProviderIsAbstractOnly(unittest.TestCase):

    def test_is_a_storage_provider_subclass(self):
        self.assertTrue(issubclass(CloudStorageProvider, StorageProvider))

    def test_cannot_instantiate_directly(self):
        # 이 Epic은 구체 구현을 하나도 만들지 않는다 - 여전히 추상이다.
        with self.assertRaises(TypeError):
            CloudStorageProvider()

    def test_future_concrete_subclass_can_still_be_instantiated(self):
        # 다음 Epic이 실제 S3/R2/GCS/Azure Provider를 만들 때 이 계약만
        # 채우면 된다는 것을 증명한다 - 이 Epic 자신은 이런 클래스를
        # 만들지 않는다(테스트 안에서만 예시로 존재).
        class _FutureS3Provider(CloudStorageProvider):
            def upload(self, local_path):
                return "s3://bucket/key"

            def delete(self, key):
                pass

            def exists(self, key):
                return True

            def public_url(self, key):
                return "https://bucket.s3.amazonaws.com/key"

            def health(self):
                from app.providers.storage.storage_provider import StorageHealth
                return StorageHealth(available=True)

        self.assertIsInstance(_FutureS3Provider(), CloudStorageProvider)
        self.assertIsInstance(_FutureS3Provider(), StorageProvider)


if __name__ == "__main__":
    unittest.main()
