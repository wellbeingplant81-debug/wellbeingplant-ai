"""
EPIC Publish Manager + Multi Platform Foundation - Platform Adapter
인터페이스.

app.services.publishing.publishing_connector.
PublishingConnector(AI Factory 3.0, 무수정)를 그대로 상속 확장한다 -
submit()/status()/cancel()/supports_platform() 4개 계약은 그대로
물려받는다. 새 Registry 타입을 만들지 않는다 - 기존 ConnectorRegistry
(무수정)가 supports_platform()/submit() 등만 duck typing으로 호출하므로,
PublishPlatform 구현체도 그 안에 그대로 등록/조회될 수 있다.

capability 질의 메서드 4개(supports_schedule/supports_thumbnail/
supports_playlist/supports_shorts)만 새로 추가한다 - Instagram/TikTok처럼
YouTube와 지원 범위가 다른 플랫폼이 늘어날 때, 호출자가 실제로 시도해
실패하기 전에 "이 플랫폼이 이 기능을 지원하는가"를 미리 물어볼 수 있게
한다.
"""

from abc import abstractmethod

from app.services.publishing.publishing_connector import (
    PublishingConnector,
)


class PublishPlatform(PublishingConnector):

    @abstractmethod
    def supports_schedule(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def supports_thumbnail(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def supports_playlist(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def supports_shorts(self) -> bool:
        raise NotImplementedError
