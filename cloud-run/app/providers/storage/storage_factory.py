"""
Sprint99 - Storage Provider 조립 (Epic 51).

OneDrive 저장소의 storage_provider_factory.py와 같은 자리이고, 같은
결정 로직이다 - provider_type이 "local"/"nas"면 LocalStorageProvider,
그 외에는 S3CompatibleStorageProvider.

원본을 그대로 가져오지 못한 이유가 하나 있다. 원본은 결정의 입력을
app.models.desktop_settings.StorageConfig에서 받는데, 그것은 Qt
데스크톱 앱의 설정 모델이다. 이 저장소에는 Qt가 없고 가져오지도
않는다(Sprint90/91/97에서 desktop 계층을 계속 잘라낸 것과 같은 이유).

그래서 입력만 환경변수로 바꿨다. 판정 규칙과 조립 결과는 원본과
같다 - 새 Storage 구현을 만들지 않는다.

이 저장소가 이미 쓰는 관례를 그대로 따른다 - 환경변수 + 합리적
기본값(youtube_upload_step_service, instagram_oauth_manager와 동일).

    STORAGE_PROVIDER          local | nas | s3  (기본 local)
    STORAGE_S3_ENDPOINT_URL
    STORAGE_S3_BUCKET
    STORAGE_S3_REGION
    STORAGE_S3_ACCESS_KEY
    STORAGE_S3_SECRET_KEY
    STORAGE_S3_PUBLIC_BASE_URL

기본값이 local인 것은 이 저장소의 실제 상태를 정직하게 반영한다 -
공개 호스팅 인프라가 아직 없다. LocalStorageProvider.public_url()은
빈 문자열을 돌려주고, 그것을 받은 쪽(Instagram 경로)은 "공개 URL이
없다"는 사실을 그대로 알게 된다. 없는 URL을 지어내지 않는다.
"""

import os

from app.providers.storage.storage_provider import StorageProvider

LOCAL_PROVIDER_TYPES = ("local", "nas")

DEFAULT_PROVIDER_TYPE = "local"


def provider_type() -> str:
    return os.environ.get("STORAGE_PROVIDER", DEFAULT_PROVIDER_TYPE).strip().lower()


def build_storage_provider(provider: str = None) -> StorageProvider:
    """
    지금 설정된 저장소를 만든다.

    무거운 것은 필요할 때만 들인다 - S3를 쓰지 않는 실행에서 boto3가
    로드되지 않는다(파이프라인이 Upload Core를 안 끌고 오게 한 것과
    같은 이유).
    """

    selected = (provider or provider_type()).strip().lower()

    if selected in LOCAL_PROVIDER_TYPES:
        from app.providers.storage.local_storage_provider import LocalStorageProvider

        return LocalStorageProvider()

    from app.providers.storage.s3_compatible_storage_config import (
        build_config_from_env,
    )
    from app.providers.storage.s3_compatible_storage_provider import (
        S3CompatibleStorageProvider,
    )

    return S3CompatibleStorageProvider(build_config_from_env())


def build_asset_publisher():
    """
    AssetPublisher까지 조립한다.

    StorageAssetPublisher는 StorageProvider를 직접 고르지 않고 주입받는다
    (원본의 설계). 그 주입을 여기서 한다.
    """

    from app.providers.storage.storage_asset_publisher import StorageAssetPublisher

    return StorageAssetPublisher(build_storage_provider())
