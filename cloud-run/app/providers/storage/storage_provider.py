"""
EPIC AssetPublisher (Production Infrastructure) - StorageProvider 인터페이스.

"Render Engine -> AssetPublisher -> StorageProvider -> AssetReference"의
가장 아래 계층이다. 이 인터페이스는 어떤 구체 저장소(로컬 파일 시스템/
AWS S3/Cloudflare R2/Google Cloud Storage/Azure Blob/NAS/사내 파일
서버)인지 전혀 모른다 - 그래서 새 저장소가 필요해지면 이 5개 메서드만
구현하는 새 클래스를 추가하면 된다(AssetPublisher/PublishManager/
Adapter 어느 것도 수정할 필요가 없다).

upload()는 local_path의 파일을 저장하고, 이후 exists()/delete()/
public_url()이 그 저장물을 다시 찾을 수 있는 key(문자열)를 돌려준다 -
key의 구체적인 모양(경로/객체 키/URL 등)은 구현체마다 다를 수 있다.

public_url()은 공개 URL을 지원하지 않는 저장소(LocalStorageProvider
등)에서는 빈 문자열을 돌려준다 - 예외를 던지지 않는다. "공개 URL이
없다"는 사실 자체가 호출자(AssetPublisher/Instagram Adapter)에게
유효한 정보이기 때문이다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StorageHealth:

    available: bool
    message: str = ""


class StorageProvider(ABC):

    @abstractmethod
    def upload(self, local_path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def public_url(self, key: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> StorageHealth:
        raise NotImplementedError
