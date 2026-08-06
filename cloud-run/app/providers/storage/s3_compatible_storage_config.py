"""
EPIC S3-Compatible Storage Provider (Production) - 설정 분리.

"Provider 내부에 하드코딩하지 않는다" - endpoint_url/bucket/region/
access_key/secret_key/public_base_url 6개 값은 전부 이 설정 객체를
통해서만 S3CompatibleStorageProvider에 주입된다.

이름과 환경 변수 접두어(STORAGE_S3_*)에 일부러 AWS/Cloudflare/MinIO
어떤 이름도 넣지 않았다 - endpoint_url만 바꾸면 AWS S3든 Cloudflare
R2든 MinIO든 똑같이 이 설정 하나로 구성된다("설정만 바꾸면 사용할 수
있어야 한다"). app.providers.upload.instagram_oauth_service.py 등이
이미 쓰는 "환경 변수 + 합리적 기본값" 관례를 그대로 따른다.
"""

import os
from dataclasses import dataclass


@dataclass
class S3CompatibleStorageConfig:

    endpoint_url: str
    bucket: str
    region: str
    access_key: str
    secret_key: str
    public_base_url: str = ""


def build_config_from_env() -> S3CompatibleStorageConfig:
    return S3CompatibleStorageConfig(
        endpoint_url=os.environ.get("STORAGE_S3_ENDPOINT_URL", ""),
        bucket=os.environ.get("STORAGE_S3_BUCKET", ""),
        region=os.environ.get("STORAGE_S3_REGION", ""),
        access_key=os.environ.get("STORAGE_S3_ACCESS_KEY", ""),
        secret_key=os.environ.get("STORAGE_S3_SECRET_KEY", ""),
        public_base_url=os.environ.get("STORAGE_S3_PUBLIC_BASE_URL", ""),
    )
