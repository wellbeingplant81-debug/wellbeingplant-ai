"""
Sprint97 - Instagram Runtime 이식 (Epic 50, Phase 1).

OneDrive 저장소의 desktop/application/publishing/instagram_runtime.py를
가져왔다. 바꾼 것은 import 경로뿐이다 - desktop 계층을 통째로
가져오지 않으므로 Sprint91이 옮겨 둔 app/services 아래를 가리킨다.

아래는 원본 설명이다.

EPIC Instagram Production Ready - InstagramRuntimeProtocol.

"Meta Developer 등록이 끝나는 즉시 App ID와 Secret만 입력하면 Instagram
게시가 바로 동작하는 상태를 만든다" - 그러려면 지금(App ID/Secret 없음)
당장 만들 수 있는 모든 부분(InstagramAdapter/PublishManager/Provider
Factory/Setup Wizard/Health Check)을 실제 Meta 없이도 완성해 둘 수
있어야 한다. 이 인터페이스가 그 경계선이다 - Instagram Graph API/OAuth
관련 원시 동작 6개만 정의하고, PublishingPlan/ConnectorResult 같은 상위
개념은 전혀 모른다(그건 InstagramAdapter의 책임).

MockInstagramRuntime(mock_instagram_runtime.py)과 RealInstagramRuntime
(real_instagram_runtime.py, 기존 InstagramOAuthService/Graph API 호출을
그대로 감싼 것 - 새 로직 아님) 둘 다 이 계약 하나만 만족하면
InstagramAdapter 입장에서는 완전히 교체 가능하다(Interface First +
Dependency Injection).

EPIC Multi Platform Publishing Runtime - 이 Protocol이 그대로
PublishingRuntimeProtocol(publishing_runtime_protocol.py)의 표준
메서드 모양이 됐다("기존 Instagram Runtime 구조를 표준으로 사용") -
그래서 이제 이 클래스는 그 공통 부모를 상속한다(메서드 이름/시그니처
변경 없음, RealInstagramRuntime/MockInstagramRuntime 무수정). capabilities
는 Instagram Graph API의 실제 특성(2단계 Container->Publish, 공개
URL 필요, 썸네일/Shorts 지원, 예약/재생목록 미지원)을 그대로 선언한다.
"""

from abc import abstractmethod

from app.providers.upload.instagram_credential import InstagramCredential
from app.services.publishing_runtime_protocol import (
    PublishingRuntimeProtocol,
    RuntimeCapabilities,
)


class InstagramRuntimeProtocol(PublishingRuntimeProtocol):

    capabilities = RuntimeCapabilities(
        two_phase_publish=True, requires_public_url=True,
        supports_thumbnail=True, supports_shorts=True,
        supports_permalink=True,
    )

    @abstractmethod
    def login(self, account_id: str) -> InstagramCredential:
        """유효한 Credential을 돌려준다 - 저장된 토큰이 없으면 실제
        로그인을, 있지만 만료됐으면 갱신을 내부적으로 수행한다(기존
        app.providers.upload.credential_loader.get_valid_credential()과
        동일한 의미론 - RealInstagramRuntime이 그 함수를 그대로
        재사용한다). ig_user_id도 함께 채워서 돌려준다."""
        raise NotImplementedError

    @abstractmethod
    def refresh_token(self, credential: InstagramCredential) -> InstagramCredential:
        """이미 가진 Credential을 명시적으로 갱신한다(Health Check의
        "Token" 항목처럼, login() 전체를 다시 타지 않고 갱신 자체만
        확인하고 싶을 때를 위한 별도 진입점)."""
        raise NotImplementedError

    @abstractmethod
    def upload_media(
        self, credential: InstagramCredential, video_url: str,
        caption: str, cover_url: str = None, plan=None,
    ) -> str:
        """공개 video_url로 Reels Container를 생성하고 container_id를
        돌려준다. plan은 공통 Runtime 계약(PublishingRuntimeProtocol)이
        추가한 선택적 파라미터다 - Instagram Runtime은 caption 문자열만
        쓰고 그냥 무시한다(YouTube Runtime처럼 title/description/
        hashtags 구조가 그대로 필요한 플랫폼을 위한 것)."""
        raise NotImplementedError

    @abstractmethod
    def publish_media(self, credential: InstagramCredential, container_id: str) -> str:
        """완성된 Container를 실제로 게시하고 media_id를 돌려준다."""
        raise NotImplementedError

    @abstractmethod
    def get_publish_status(self, credential: InstagramCredential, container_id: str) -> str:
        """Container의 현재 status_code(예: IN_PROGRESS/FINISHED/ERROR/
        EXPIRED)를 한 번 조회한다 - 폴링 루프(sleep/timeout)는 이
        메서드의 책임이 아니다(호출자, 즉 InstagramAdapter가 반복
        호출한다)."""
        raise NotImplementedError

    @abstractmethod
    def revoke(self, credential: InstagramCredential) -> None:
        """이 계정의 로그인 상태를 지운다(로컬 로그아웃) - Meta 쪽에
        원격으로 이 로그인을 무효화하는 별도 API는 없다(추측하지
        않는다) - 저장된 Credential을 지워 다음 login()이 다시 실제
        로그인을 타게 만드는 것이 이 프로젝트가 보장할 수 있는
        전부다."""
        raise NotImplementedError
