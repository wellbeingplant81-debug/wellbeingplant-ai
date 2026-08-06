"""
Epic 46 Sprint 002 (RED) - OAuth & Channel Foundation.

기존 코드 조사 결과(코드 작성 전 확인): app/providers/upload/ 전체와
tests/를 조사했으나 OAuth/Credential/Token/Auth Service 관련 기존
구현은 전혀 없었다(문서 주석에 "OAuth는 다루지 않는다"는 명시적 제외
언급만 있었다). requirements.txt에 google-auth==2.55.1이 이미
있지만(Vertex AI genai.Client가 사용), 이번 Sprint는 Mock OAuth만
구현하므로 이 라이브러리조차 새로 import하지 않는다(Google 라이브러리
의존성 최소화).

app/providers/upload/(Sprint108-119 + Sprint001 UploadRequest)를 그대로
확장한다 - 새 Publisher 시스템/중복 Protocol/Factory/Registry/Mock/
UploadService를 만들지 않는다. UploadProvider.upload() 시그니처는
전혀 건드리지 않는다(이번 Sprint는 실제 Video Upload를 구현하지
않으므로 OAuth 계층과 UploadProvider를 연결하지도 않는다 - 연결은
이후 Sprint 범위).

계정(Account) 중심 구조 - OAuthCredential/ChannelInfo 둘 다
account_id를 갖는다. 이번 Sprint는 단일 계정만 정상 동작하면 되지만,
구조 자체는 여러 계정을 저장/조회할 수 있게 설계한다(TokenStore가
account_id로 keying).

아직 구현이 없으므로(RED) 새 클래스에 대한 테스트는 실패해야 정상.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)


DEFAULT_ACCOUNT_ID = "default"


class TestOAuthCredential(unittest.TestCase):

    def test_creation_holds_tokens_and_account_id(self):
        from app.providers.upload.oauth_credential import OAuthCredential

        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        credential = OAuthCredential(
            account_id=DEFAULT_ACCOUNT_ID,
            access_token="access-1",
            refresh_token="refresh-1",
            expires_at=expires_at,
        )

        self.assertEqual(credential.account_id, DEFAULT_ACCOUNT_ID)
        self.assertEqual(credential.access_token, "access-1")
        self.assertEqual(credential.refresh_token, "refresh-1")
        self.assertEqual(credential.expires_at, expires_at)

    def test_credential_does_not_store_password_fields(self):
        # Epic46 Sprint002 제약 - Google 계정 비밀번호는 저장하지
        # 않는다. 모델 필드에 password 관련 필드가 없어야 한다.
        from app.providers.upload.oauth_credential import OAuthCredential

        field_names = OAuthCredential.__dataclass_fields__.keys()
        for forbidden in ("password", "google_password", "credentials_password"):
            self.assertNotIn(forbidden, field_names)

    def test_is_expired_true_for_past_expiry(self):
        from app.providers.upload.oauth_credential import OAuthCredential, is_expired

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        credential = OAuthCredential(
            account_id=DEFAULT_ACCOUNT_ID,
            access_token="a",
            refresh_token="r",
            expires_at=past,
        )

        self.assertTrue(is_expired(credential))

    def test_is_expired_false_for_future_expiry(self):
        from app.providers.upload.oauth_credential import OAuthCredential, is_expired

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        credential = OAuthCredential(
            account_id=DEFAULT_ACCOUNT_ID,
            access_token="a",
            refresh_token="r",
            expires_at=future,
        )

        self.assertFalse(is_expired(credential))


class TestChannelInfo(unittest.TestCase):

    def test_creation_holds_channel_fields(self):
        from app.providers.upload.channel_info import ChannelInfo

        channel = ChannelInfo(
            account_id=DEFAULT_ACCOUNT_ID,
            channel_id="UC123",
            channel_title="Test Channel",
        )

        self.assertEqual(channel.account_id, DEFAULT_ACCOUNT_ID)
        self.assertEqual(channel.channel_id, "UC123")
        self.assertEqual(channel.channel_title, "Test Channel")


class TestMockOAuthServiceAuthenticate(unittest.TestCase):

    def test_authenticate_success_returns_credential(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService

        service = MockOAuthService()
        credential = service.authenticate(DEFAULT_ACCOUNT_ID)

        self.assertEqual(credential.account_id, DEFAULT_ACCOUNT_ID)
        self.assertTrue(credential.access_token)
        self.assertTrue(credential.refresh_token)

    def test_authenticate_failure_raises_oauth_error(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.oauth_service import OAuthError

        service = MockOAuthService(should_fail_auth=True)

        with self.assertRaises(OAuthError):
            service.authenticate(DEFAULT_ACCOUNT_ID)


class TestMockOAuthServiceRefresh(unittest.TestCase):

    def test_refresh_success_returns_new_access_token(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService

        service = MockOAuthService()
        original = service.authenticate(DEFAULT_ACCOUNT_ID)

        refreshed = service.refresh(original)

        self.assertEqual(refreshed.account_id, original.account_id)
        self.assertEqual(refreshed.refresh_token, original.refresh_token)
        self.assertNotEqual(refreshed.access_token, original.access_token)

    def test_refresh_failure_raises_oauth_error(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.oauth_service import OAuthError

        service = MockOAuthService(should_fail_refresh=True)
        original = MockOAuthService().authenticate(DEFAULT_ACCOUNT_ID)

        with self.assertRaises(OAuthError):
            service.refresh(original)


class TestMockOAuthServiceChannelInfo(unittest.TestCase):

    def test_fetch_channel_info_success(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService

        service = MockOAuthService()
        credential = service.authenticate(DEFAULT_ACCOUNT_ID)

        channel = service.fetch_channel_info(credential)

        self.assertEqual(channel.account_id, DEFAULT_ACCOUNT_ID)
        self.assertTrue(channel.channel_id)
        self.assertTrue(channel.channel_title)

    def test_fetch_channel_info_failure_raises_oauth_error(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.oauth_service import OAuthError

        service = MockOAuthService(should_fail_channel=True)
        credential = MockOAuthService().authenticate(DEFAULT_ACCOUNT_ID)

        with self.assertRaises(OAuthError):
            service.fetch_channel_info(credential)


class TestMockOAuthServiceIsOAuthService(unittest.TestCase):

    def test_mock_oauth_service_implements_protocol(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.oauth_service import OAuthService

        self.assertIsInstance(MockOAuthService(), OAuthService)

    def test_oauth_service_is_abstract(self):
        from app.providers.upload.oauth_service import OAuthService

        with self.assertRaises(TypeError):
            OAuthService()


class TestTokenStore(unittest.TestCase):

    def test_save_and_load_round_trip(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.token_store import TokenStore

        store = TokenStore()
        credential = MockOAuthService().authenticate(DEFAULT_ACCOUNT_ID)

        store.save(credential)
        loaded = store.load(DEFAULT_ACCOUNT_ID)

        self.assertEqual(loaded, credential)

    def test_load_missing_account_returns_none(self):
        from app.providers.upload.token_store import TokenStore

        store = TokenStore()

        self.assertIsNone(store.load("nonexistent-account"))

    def test_store_supports_multiple_accounts(self):
        # 멀티 계정 UI는 이번 Sprint 범위가 아니지만, 구조 자체는
        # 여러 계정을 독립적으로 저장/조회할 수 있어야 한다.
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.token_store import TokenStore

        store = TokenStore()
        service = MockOAuthService()
        cred_a = service.authenticate("account-a")
        cred_b = service.authenticate("account-b")

        store.save(cred_a)
        store.save(cred_b)

        self.assertEqual(store.load("account-a").account_id, "account-a")
        self.assertEqual(store.load("account-b").account_id, "account-b")


class TestCredentialLoader(unittest.TestCase):

    def test_authenticates_when_no_credential_stored(self):
        from app.providers.upload.credential_loader import get_valid_credential
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.token_store import TokenStore

        service = MockOAuthService()
        store = TokenStore()

        credential = get_valid_credential(service, store, DEFAULT_ACCOUNT_ID)

        self.assertEqual(credential.account_id, DEFAULT_ACCOUNT_ID)
        self.assertEqual(store.load(DEFAULT_ACCOUNT_ID), credential)

    def test_returns_stored_credential_when_not_expired(self):
        from app.providers.upload.credential_loader import get_valid_credential
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.token_store import TokenStore

        service = MockOAuthService()
        store = TokenStore()
        first = get_valid_credential(service, store, DEFAULT_ACCOUNT_ID)

        second = get_valid_credential(service, store, DEFAULT_ACCOUNT_ID)

        self.assertEqual(first.access_token, second.access_token)

    def test_refreshes_when_expired(self):
        from app.providers.upload.credential_loader import get_valid_credential
        from app.providers.upload.mock_oauth_service import MockOAuthService
        from app.providers.upload.oauth_credential import OAuthCredential
        from app.providers.upload.token_store import TokenStore

        service = MockOAuthService()
        store = TokenStore()
        expired = OAuthCredential(
            account_id=DEFAULT_ACCOUNT_ID,
            access_token="stale-access",
            refresh_token="stale-refresh",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        store.save(expired)

        refreshed = get_valid_credential(service, store, DEFAULT_ACCOUNT_ID)

        self.assertNotEqual(refreshed.access_token, "stale-access")
        self.assertEqual(
            store.load(DEFAULT_ACCOUNT_ID).access_token, refreshed.access_token
        )


class TestExistingUploadProviderUnaffected(unittest.TestCase):
    """기존 UploadProvider 영향 없음 - Sprint001/기존 Distribution 파일이
    OAuth 계층 추가 후에도 그대로 동작하는지 재확인한다."""

    def test_mock_upload_provider_unaffected(self):
        from app.providers.upload.mock_upload_provider import MockUploadProvider

        provider = MockUploadProvider()
        result = provider.upload("output/video.mp4", {"title": "t"})

        self.assertTrue(result.success)

    def test_upload_request_unaffected(self):
        from app.providers.upload.upload_request import UploadRequest

        request = UploadRequest(file_path="output/video.mp4", metadata={"title": "t"})

        self.assertEqual(request.file_path, "output/video.mp4")

    def test_factory_still_returns_mock_provider(self):
        from app.providers.upload.mock_upload_provider import MockUploadProvider
        from app.providers.upload.provider_factory import UploadProviderFactory

        provider = UploadProviderFactory().create("mock")

        self.assertIsInstance(provider, MockUploadProvider)


if __name__ == "__main__":
    unittest.main()
