"""
AI Factory 3.0, Part 1 - Publishing Connector Interface.

Connector는 이 4개 메서드만 제공한다 - 그 이상도 이하도 아니다. 실제
Network 호출을 하는 Connector(YouTube API 등)는 이 배치의 범위 밖이다
("YouTube API 금지", "Network 호출 금지") - 지금은 이 인터페이스를
구현하는 것이 MockConnector 하나뿐이다.
"""

from abc import ABC, abstractmethod

from app.services.publishing.connector_result import ConnectorResult


class PublishingConnector(ABC):

    @abstractmethod
    def submit(self, plan) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def cancel(self, external_id: str) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def status(self, external_id: str) -> ConnectorResult:
        raise NotImplementedError

    @abstractmethod
    def supports_platform(self, platform: str) -> bool:
        raise NotImplementedError
