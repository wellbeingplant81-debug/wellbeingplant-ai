"""
Epic 47 Sprint 005 - AI Metadata Engine, Playlist Recommendation.

Epic 27 Recommendation Intelligence와 동일한 원칙 - 근거 없는 권장사항은
생성하지 않는다. reason은 항상 채워진다.
"""

from dataclasses import dataclass


@dataclass
class PlaylistRecommendation:
    playlist_title: str
    reason: str
