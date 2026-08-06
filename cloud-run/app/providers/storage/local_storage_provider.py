"""
EPIC AssetPublisher (Production Infrastructure) - LocalStorageProvider.

현재 이 프로젝트의 실제 기본 구현체다 - 실제 업로드를 하지 않는다
(Network 호출 없음). upload()는 파일이 실제로 존재하는지만 확인하고,
key로 원본 local_path를 그대로 돌려준다("업로드"가 아니라 "이미 여기
있다"는 사실만 확인한다). public_url()은 항상 빈 문자열이다 - 로컬
파일 시스템은 구조적으로 공개 URL을 가질 수 없다(이 사실 자체가
Instagram 업로드가 아직 안 되는 이유다, 지어내지 않는다).

delete()는 실제로 파일을 지우지 않는다 - 이 Provider가 만든 사본이
아니라 사용자의 원본 렌더링 결과물이기 때문이다(관리 책임 밖).
"""

import os

from app.providers.storage.storage_provider import StorageHealth, StorageProvider


class LocalStorageProvider(StorageProvider):

    def upload(self, local_path: str) -> str:
        if not os.path.exists(local_path):
            raise FileNotFoundError(local_path)
        return local_path

    def delete(self, key: str) -> None:
        pass

    def exists(self, key: str) -> bool:
        return os.path.exists(key)

    def public_url(self, key: str) -> str:
        return ""

    def health(self) -> StorageHealth:
        return StorageHealth(available=True, message="로컬 파일 시스템")
