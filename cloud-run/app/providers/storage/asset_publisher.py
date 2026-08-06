"""
EPIC Instagram Connector (Production) - AssetPublisher 인터페이스.

역할은 정확히 하나뿐이다 - publish(local_path) -> AssetReference.
"이 로컬 파일을 각 플랫폼이 실제로 요구하는 형태(local_path 그대로
또는 공개 URL)로 바꿔 달라"는 요청이다. 구현체가 실제로 무엇을
하는지(아무 것도 안 하고 로컬 경로만 확인/그대로 감싸는지, 실제
클라우드에 업로드해 공개 URL을 만드는지)는 이 인터페이스가 알 바 아니다.

Instagram Connector 전용으로 만든 것이 아니다 - desktop.application.
publishing.publish_manager.PublishManager가 구성 시점(build_default_
adapter_registry())에만 필요한 Adapter에게 주입한다. 어떤 Adapter도
이 인터페이스를 강제로 쓸 필요는 없다(YouTubeAdapter는 이번 Epic에서
쓰지 않는다 - "YouTube Connector 수정 최소화").
"""

from abc import ABC, abstractmethod

from app.providers.storage.asset_reference import AssetReference


class AssetPublisher(ABC):

    @abstractmethod
    def publish(self, local_path: str) -> AssetReference:
        raise NotImplementedError
