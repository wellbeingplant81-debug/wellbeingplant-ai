"""
EPIC AssetPublisher (Production Infrastructure) - MockStorageProvider.

테스트 전용이다 - desktop.application.publishing.connectors.
mock_connector.MockConnector와 동일한 관례를 따른다: 실제 프로덕션
기본 경로(desktop.application.publishing.publish_manager.
build_default_adapter_registry() 등)는 이 클래스를 조립하지 않는다 -
테스트 코드가 명시적으로 구성할 때만 쓰인다. 실제 Network 호출은
어디에도 없다 - 메모리 dict만으로 upload/exists/delete/public_url을
흉내낸다.
"""

import os

from app.providers.storage.storage_provider import StorageHealth, StorageProvider

_DEFAULT_URL_TEMPLATE = "https://mock.storage.local/{key}"


class MockStorageProvider(StorageProvider):

    def __init__(
        self, public_url_template: str = _DEFAULT_URL_TEMPLATE, should_fail: bool = False,
    ):
        self._public_url_template = public_url_template
        self.should_fail = should_fail
        self._uploaded: dict[str, str] = {}

    def upload(self, local_path: str) -> str:
        if self.should_fail:
            raise RuntimeError("Mock storage upload failed")
        key = os.path.basename(local_path)
        self._uploaded[key] = local_path
        return key

    def delete(self, key: str) -> None:
        self._uploaded.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._uploaded

    def public_url(self, key: str) -> str:
        return self._public_url_template.format(key=key)

    def health(self) -> StorageHealth:
        if self.should_fail:
            return StorageHealth(available=False, message="Mock storage configured to fail")
        return StorageHealth(available=True, message="Mock storage")
