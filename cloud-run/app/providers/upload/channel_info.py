"""
Epic 46 Sprint 002 - OAuth & Channel Foundation.

OAuth Credential로 조회한 YouTube 채널의 최소 식별 정보. account_id를
가져 어느 계정의 채널인지 항상 추적 가능하게 한다.
"""

from dataclasses import dataclass


@dataclass
class ChannelInfo:
    account_id: str
    channel_id: str
    channel_title: str
