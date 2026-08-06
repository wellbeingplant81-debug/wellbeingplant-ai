"""
EPIC S3-Compatible Storage Provider (Production) (RED->GREEN) -
desktop/application/assets/s3_compatible_storage_config.py.

"Provider 내부에 하드코딩하지 않는다" - endpoint_url/bucket/region/
access_key/secret_key/public_base_url 6개 값은 전부 이 설정 객체를
통해서만 주입된다. build_config_from_env()는 환경 변수로도 구성할 수
있게 한다(YouTube/Instagram Provider들이 이미 쓰는 것과 동일한 관례) -
"S3용"이 아니라 "이 값들을 요구하는 아무 S3-Compatible 서비스용"이라는
점을 이름에서부터 드러낸다(AWS/R2/MinIO 전용 이름을 쓰지 않는다).
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.storage.s3_compatible_storage_config import (
    S3CompatibleStorageConfig,
    build_config_from_env,
)


class TestS3CompatibleStorageConfig(unittest.TestCase):

    def test_all_fields_are_stored_as_given(self):
        config = S3CompatibleStorageConfig(
            endpoint_url="https://s3.amazonaws.com",
            bucket="my-bucket",
            region="us-east-1",
            access_key="AKIA...",
            secret_key="secret",
            public_base_url="https://cdn.example.com",
        )

        self.assertEqual(config.endpoint_url, "https://s3.amazonaws.com")
        self.assertEqual(config.bucket, "my-bucket")
        self.assertEqual(config.region, "us-east-1")
        self.assertEqual(config.access_key, "AKIA...")
        self.assertEqual(config.secret_key, "secret")
        self.assertEqual(config.public_base_url, "https://cdn.example.com")

    def test_public_base_url_defaults_to_empty(self):
        config = S3CompatibleStorageConfig(
            endpoint_url="https://s3.amazonaws.com", bucket="b",
            region="us-east-1", access_key="a", secret_key="s",
        )
        self.assertEqual(config.public_base_url, "")


class TestBuildConfigFromEnv(unittest.TestCase):

    def test_reads_all_values_from_env_vars(self):
        env = {
            "STORAGE_S3_ENDPOINT_URL": "https://abc123.r2.cloudflarestorage.com",
            "STORAGE_S3_BUCKET": "wellbeingplant-assets",
            "STORAGE_S3_REGION": "auto",
            "STORAGE_S3_ACCESS_KEY": "r2-access-key",
            "STORAGE_S3_SECRET_KEY": "r2-secret-key",
            "STORAGE_S3_PUBLIC_BASE_URL": "https://assets.wellbeingplant.example",
        }
        with patch.dict(os.environ, env, clear=True):
            config = build_config_from_env()

        self.assertEqual(config.endpoint_url, "https://abc123.r2.cloudflarestorage.com")
        self.assertEqual(config.bucket, "wellbeingplant-assets")
        self.assertEqual(config.region, "auto")
        self.assertEqual(config.access_key, "r2-access-key")
        self.assertEqual(config.secret_key, "r2-secret-key")
        self.assertEqual(config.public_base_url, "https://assets.wellbeingplant.example")

    def test_missing_env_vars_default_to_empty_strings_not_crash(self):
        with patch.dict(os.environ, {}, clear=True):
            config = build_config_from_env()

        self.assertEqual(config.endpoint_url, "")
        self.assertEqual(config.bucket, "")
        self.assertEqual(config.access_key, "")
        self.assertEqual(config.secret_key, "")

    def test_no_credentials_hardcoded_in_module_source(self):
        # "Provider 내부에 하드코딩하지 않는다"를 소스 코드 수준에서
        # 직접 확인한다 - access_key/secret_key처럼 보이는 실제 값
        # 리터럴이 이 파일 안에 없어야 한다.
        # Sprint99 - 원본은 경로를 문자열로 조립했다("desktop/application/
        # assets/..."). 이식하면서 그 경로가 사라졌으므로 모듈 자신에게
        # 물어본다 - 다음에 또 옮겨도 따라온다.
        from app.providers.storage import s3_compatible_storage_config

        with open(s3_compatible_storage_config.__file__, "r", encoding="utf-8") as f:
            source = f.read()

        self.assertNotIn("AKIA", source)  # 실제 AWS Access Key 접두어.


if __name__ == "__main__":
    unittest.main()
