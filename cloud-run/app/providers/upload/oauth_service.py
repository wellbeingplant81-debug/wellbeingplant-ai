"""
Epic 46 Sprint 002 - OAuth & Channel Foundation.

Google OAuth 인증/Token 갱신/Channel 조회를 추상화하는 Protocol이다.
app/providers/upload/upload_provider.py(UploadProvider)와 동일한
스타일(ABC + 최소 메서드 집합)을 따른다. 실제 Google API 호출은 이
계층 뒤에 숨겨진다 - 이번 Sprint의 유일한 구현체(MockOAuthService)는
실제 네트워크 호출을 전혀 하지 않는다.

이 파일이 하지 않는 것:
- 실제 Google OAuth 플로우/브라우저 동의 화면
- 실제 YouTube Data API 호출
- Video Upload(app/providers/upload/upload_provider.py 소관, 연결하지
  않는다 - 이번 Sprint 범위 밖)
"""

from abc import ABC, abstractmethod

from app.providers.upload.channel_info import ChannelInfo
from app.providers.upload.oauth_credential import OAuthCredential


class OAuthError(Exception):
    pass


class OAuthService(ABC):

    @abstractmethod
    def authenticate(self, account_id: str) -> OAuthCredential:
        raise NotImplementedError

    @abstractmethod
    def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        raise NotImplementedError

    @abstractmethod
    def fetch_channel_info(self, credential: OAuthCredential) -> ChannelInfo:
        raise NotImplementedError
