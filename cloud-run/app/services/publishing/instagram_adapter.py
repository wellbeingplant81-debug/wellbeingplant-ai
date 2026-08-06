"""
EPIC Instagram Connector (Production) - Instagram Adapter.
EPIC Instagram Production Ready - InstagramRuntimeProtocol Injection.
EPIC Multi Platform Publishing Runtime - RuntimeBackedPublishAdapter로
일반화.

이 클래스는 이제 app.services.publishing.
runtime_backed_publish_adapter.RuntimeBackedPublishAdapter의 얇은
서브클래스일 뿐이다 - Dry Run/Pipeline Trace/실패 분류 등 실제
오케스트레이션 로직은 전부 그 부모 클래스에 있다("Platform별 특수처리
제거" - InstagramAdapter 자신이 갖고 있던 것은 이제 "Instagram 전용
Runtime 기본 생성(_build_default_runtime)"뿐이다). 클래스 이름/생성자
시그니처(asset_publisher/poll_interval_seconds/poll_timeout_seconds/
runtime)는 100% 그대로 유지한다(app.services.publishing.
publish_manager.py와 기존 테스트가 이미 이 이름/시그니처를 참조 -
Regression Zero).

runtime을 주입하지 않으면(기존 호출부와 100% 동일하게) 환경변수 기반
RealInstagramRuntime을 스스로 만든다 - Mock으로 바꾸려면
runtime=MockInstagramRuntime()만 주입하면 된다(Dependency Injection).
"""

import os

from app.providers.upload.instagram_oauth_service import InstagramOAuthService
from app.providers.upload.instagram_token_store import InstagramTokenStore
from app.services.publishing.runtime_backed_publish_adapter import (
    RuntimeBackedPublishAdapter,
)
from app.services.real_instagram_runtime import RealInstagramRuntime

_DEFAULT_POLL_INTERVAL_SECONDS = 3
_DEFAULT_POLL_TIMEOUT_SECONDS = 300


def _default_client_id() -> str:
    return os.environ.get("INSTAGRAM_OAUTH_CLIENT_ID", "")


def _default_client_secret() -> str:
    return os.environ.get("INSTAGRAM_OAUTH_CLIENT_SECRET", "")


def _default_redirect_uri() -> str:
    return os.environ.get("INSTAGRAM_OAUTH_REDIRECT_URI", "http://localhost:8551/callback")


def _default_token_store_path() -> str:
    return os.environ.get(
        "INSTAGRAM_OAUTH_TOKEN_STORE_PATH", "credentials/instagram_oauth_tokens.json",
    )


def _build_default_runtime() -> RealInstagramRuntime:
    return RealInstagramRuntime(
        client_id=_default_client_id(), client_secret=_default_client_secret(),
        redirect_uri=_default_redirect_uri(),
        token_store=InstagramTokenStore(storage_path=_default_token_store_path()),
        oauth_service_factory=InstagramOAuthService,
    )


class InstagramAdapter(RuntimeBackedPublishAdapter):

    def __init__(
        self, asset_publisher=None,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
        poll_timeout_seconds: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
        runtime=None,
    ):
        super().__init__(
            platform="Instagram",
            runtime=runtime if runtime is not None else _build_default_runtime(),
            asset_publisher=asset_publisher,
            poll_interval_seconds=poll_interval_seconds,
            poll_timeout_seconds=poll_timeout_seconds,
        )
