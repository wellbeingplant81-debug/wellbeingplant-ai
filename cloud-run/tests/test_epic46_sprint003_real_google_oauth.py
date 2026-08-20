"""
Epic 46 Sprint 003 (RED) - Real Google OAuth Integration.

GoogleOAuthService는 Sprint002의 OAuthService ABC를 구현하는 실제
구현체다 - MockOAuthService(무수정, 그대로 유지)와 나란히 존재한다.
Desktop Application Flow(InstalledAppFlow)를 쓰되, 실제 브라우저 로그인/
네트워크 호출은 이 테스트 전체에서 전부 Mock 처리한다(진짜 로그인은
이 Sprint 완료 후 사용자가 직접 실행한다).

FileTokenStore는 Sprint002 TokenStore(In-Memory)와 동일한 save/load
인터페이스를 갖는 파일 기반 구현체다 - "프로그램 재시작"은 새
FileTokenStore 인스턴스를 같은 경로로 다시 만드는 것으로 시뮬레이션
한다(실제 프로세스 재시작 없이도 영속성을 검증할 수 있다).

Client Secret은 절대 코드에 하드코딩하지 않는다 - 테스트도 임시
파일(tempfile)에 가짜 client_secret.json을 써서 검증한다.

아직 구현이 없으므로(RED) 새 클래스에 대한 테스트는 실패해야 정상.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)


DEFAULT_ACCOUNT_ID = "default"

FAKE_CLIENT_SECRET = {
    "installed": {
        "client_id": "fake-client-id.apps.googleusercontent.com",
        "client_secret": "fake-client-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


def _write_fake_client_secret(tmp_dir: str) -> str:
    path = os.path.join(tmp_dir, "client_secret.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(FAKE_CLIENT_SECRET, f)
    return path


def _fake_google_credentials(
    access_token="fresh-access-token", refresh_token="fresh-refresh-token"
):
    credentials = MagicMock()
    credentials.token = access_token
    credentials.refresh_token = refresh_token
    credentials.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        hours=1
    )
    return credentials


class TestGoogleOAuthServiceIsOAuthService(unittest.TestCase):

    def test_implements_oauth_service_protocol(self):
        from app.providers.upload.google_oauth_service import GoogleOAuthService
        from app.providers.upload.oauth_service import OAuthService

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = GoogleOAuthService(
                client_secret_path=_write_fake_client_secret(tmp_dir)
            )

        self.assertIsInstance(service, OAuthService)


class TestGoogleOAuthServiceAuthenticate(unittest.TestCase):

    def test_authenticate_runs_installed_app_flow_and_returns_credential(self):
        from app.providers.upload.google_oauth_service import GoogleOAuthService

        with tempfile.TemporaryDirectory() as tmp_dir:
            client_secret_path = _write_fake_client_secret(tmp_dir)
            service = GoogleOAuthService(client_secret_path=client_secret_path)

            fake_flow = MagicMock()
            fake_flow.run_local_server.return_value = _fake_google_credentials()

            with patch(
                "app.providers.upload.google_oauth_service.InstalledAppFlow.from_client_secrets_file",
                return_value=fake_flow,
            ) as mock_from_file:
                credential = service.authenticate(DEFAULT_ACCOUNT_ID)

        mock_from_file.assert_called_once()
        called_path = mock_from_file.call_args.args[0]
        self.assertEqual(called_path, client_secret_path)
        fake_flow.run_local_server.assert_called_once()

        self.assertEqual(credential.account_id, DEFAULT_ACCOUNT_ID)
        self.assertEqual(credential.access_token, "fresh-access-token")
        self.assertEqual(credential.refresh_token, "fresh-refresh-token")

    def test_authenticate_requests_read_upload_and_playlist_scopes(self):
        """
        세 가지가 각각 다른 일을 한다. 하나라도 빠지면 그 일만 조용히
        403 이 되고, 나머지는 멀쩡해서 원인을 찾기 어렵다.

            youtube.readonly   채널 조회
            youtube.upload     영상 올리기
            youtube            재생목록 만들기·넣기

        2026-07-21 - youtube.upload 가 없으면 업로드가 늘
        insufficientPermissions 로 실패하는 것을 실제 운영에서 확인해
        더했다.

        Sprint251 - 같은 일이 재생목록에서 되풀이됐다. Sprint247 의 실제
        업로드는 성공했는데 재생목록 단계만 403 "insufficient
        authentication scopes" 로 죽었다. 공식 문서를 보면
        playlists.insert 와 playlistItems.insert 의 허용 목록에
        youtube.upload 가 아예 없다 - 그 자리에 필요한 것은 youtube 다.

        force-ssl 이나 youtubepartner 가 아니라 youtube 를 고른 것은
        셋 중 가장 좁으면서 재생목록 읽기·쓰기에 충분하기 때문이다.
        """

        from app.providers.upload.google_oauth_service import GoogleOAuthService

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = GoogleOAuthService(
                client_secret_path=_write_fake_client_secret(tmp_dir)
            )

            fake_flow = MagicMock()
            fake_flow.run_local_server.return_value = _fake_google_credentials()

            with patch(
                "app.providers.upload.google_oauth_service.InstalledAppFlow.from_client_secrets_file",
                return_value=fake_flow,
            ) as mock_from_file:
                service.authenticate(DEFAULT_ACCOUNT_ID)

        scopes = mock_from_file.call_args.kwargs["scopes"]
        self.assertEqual(
            scopes,
            [
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube",
            ],
        )

    def test_authenticate_failure_raises_oauth_error(self):
        from app.providers.upload.google_oauth_service import GoogleOAuthService
        from app.providers.upload.oauth_service import OAuthError

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = GoogleOAuthService(
                client_secret_path=_write_fake_client_secret(tmp_dir)
            )

            with patch(
                "app.providers.upload.google_oauth_service.InstalledAppFlow.from_client_secrets_file",
                side_effect=RuntimeError("browser closed"),
            ):
                with self.assertRaises(OAuthError):
                    service.authenticate(DEFAULT_ACCOUNT_ID)


class TestGoogleOAuthServiceRefresh(unittest.TestCase):

    def test_refresh_success_returns_new_access_token(self):
        from app.providers.upload.google_oauth_service import GoogleOAuthService
        from app.providers.upload.oauth_credential import OAuthCredential

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = GoogleOAuthService(
                client_secret_path=_write_fake_client_secret(tmp_dir)
            )

            stale = OAuthCredential(
                account_id=DEFAULT_ACCOUNT_ID,
                access_token="stale-token",
                refresh_token="stale-refresh",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )

            def _refresh_side_effect(self_credentials, request):
                self_credentials.token = "refreshed-token"
                self_credentials.expiry = datetime.now(timezone.utc).replace(
                    tzinfo=None
                ) + timedelta(hours=1)

            with patch(
                "app.providers.upload.google_oauth_service.Credentials.refresh",
                new=_refresh_side_effect,
            ):
                refreshed = service.refresh(stale)

        self.assertEqual(refreshed.access_token, "refreshed-token")
        self.assertEqual(refreshed.refresh_token, "stale-refresh")
        self.assertEqual(refreshed.account_id, DEFAULT_ACCOUNT_ID)

    def test_refresh_failure_raises_oauth_error(self):
        from app.providers.upload.google_oauth_service import GoogleOAuthService
        from app.providers.upload.oauth_credential import OAuthCredential
        from app.providers.upload.oauth_service import OAuthError

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = GoogleOAuthService(
                client_secret_path=_write_fake_client_secret(tmp_dir)
            )

            stale = OAuthCredential(
                account_id=DEFAULT_ACCOUNT_ID,
                access_token="stale-token",
                refresh_token="invalid-refresh",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )

            with patch(
                "app.providers.upload.google_oauth_service.Credentials.refresh",
                side_effect=RuntimeError("invalid_grant"),
            ):
                with self.assertRaises(OAuthError):
                    service.refresh(stale)


class TestGoogleOAuthServiceChannelInfo(unittest.TestCase):

    def _credential(self):
        from app.providers.upload.oauth_credential import OAuthCredential

        return OAuthCredential(
            account_id=DEFAULT_ACCOUNT_ID,
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    def test_fetch_channel_info_success(self):
        from app.providers.upload.google_oauth_service import GoogleOAuthService

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = GoogleOAuthService(
                client_secret_path=_write_fake_client_secret(tmp_dir)
            )

            fake_youtube = MagicMock()
            fake_youtube.channels.return_value.list.return_value.execute.return_value = {
                "items": [
                    {"id": "UC_real_channel", "snippet": {"title": "My Real Channel"}}
                ],
            }

            with patch(
                "app.providers.upload.google_oauth_service.build",
                return_value=fake_youtube,
            ):
                channel = service.fetch_channel_info(self._credential())

        self.assertEqual(channel.account_id, DEFAULT_ACCOUNT_ID)
        self.assertEqual(channel.channel_id, "UC_real_channel")
        self.assertEqual(channel.channel_title, "My Real Channel")

    def test_fetch_channel_info_no_channel_raises_oauth_error(self):
        from app.providers.upload.google_oauth_service import GoogleOAuthService
        from app.providers.upload.oauth_service import OAuthError

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = GoogleOAuthService(
                client_secret_path=_write_fake_client_secret(tmp_dir)
            )

            fake_youtube = MagicMock()
            fake_youtube.channels.return_value.list.return_value.execute.return_value = {
                "items": []
            }

            with patch(
                "app.providers.upload.google_oauth_service.build",
                return_value=fake_youtube,
            ):
                with self.assertRaises(OAuthError):
                    service.fetch_channel_info(self._credential())

    def test_fetch_channel_info_api_error_raises_oauth_error(self):
        from app.providers.upload.google_oauth_service import GoogleOAuthService
        from app.providers.upload.oauth_service import OAuthError

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = GoogleOAuthService(
                client_secret_path=_write_fake_client_secret(tmp_dir)
            )

            with patch(
                "app.providers.upload.google_oauth_service.build",
                side_effect=RuntimeError("network error"),
            ):
                with self.assertRaises(OAuthError):
                    service.fetch_channel_info(self._credential())


class TestFileTokenStore(unittest.TestCase):

    def test_save_and_load_round_trip(self):
        from app.providers.upload.file_token_store import FileTokenStore
        from app.providers.upload.oauth_credential import OAuthCredential

        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = os.path.join(tmp_dir, "tokens.json")
            store = FileTokenStore(storage_path=storage_path)
            credential = OAuthCredential(
                account_id=DEFAULT_ACCOUNT_ID,
                access_token="a",
                refresh_token="r",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )

            store.save(credential)
            loaded = store.load(DEFAULT_ACCOUNT_ID)

        self.assertEqual(loaded.account_id, credential.account_id)
        self.assertEqual(loaded.access_token, credential.access_token)
        self.assertEqual(loaded.refresh_token, credential.refresh_token)

    def test_load_missing_account_returns_none(self):
        from app.providers.upload.file_token_store import FileTokenStore

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FileTokenStore(storage_path=os.path.join(tmp_dir, "tokens.json"))

            self.assertIsNone(store.load("nonexistent"))

    def test_credential_restored_after_program_restart_simulation(self):
        # "프로그램 재시작 후 Credential 복원" - 새 FileTokenStore 인스턴스를
        # 같은 파일 경로로 다시 만들어 재시작을 시뮬레이션한다.
        from app.providers.upload.file_token_store import FileTokenStore
        from app.providers.upload.oauth_credential import OAuthCredential

        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = os.path.join(tmp_dir, "tokens.json")
            first_process_store = FileTokenStore(storage_path=storage_path)
            credential = OAuthCredential(
                account_id=DEFAULT_ACCOUNT_ID,
                access_token="persisted-access",
                refresh_token="persisted-refresh",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            first_process_store.save(credential)

            # "재시작" - 완전히 새로운 인스턴스, 메모리 공유 없음.
            second_process_store = FileTokenStore(storage_path=storage_path)
            restored = second_process_store.load(DEFAULT_ACCOUNT_ID)

        self.assertEqual(restored.access_token, "persisted-access")
        self.assertEqual(restored.refresh_token, "persisted-refresh")

    def test_store_supports_multiple_accounts(self):
        from app.providers.upload.file_token_store import FileTokenStore
        from app.providers.upload.oauth_credential import OAuthCredential

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FileTokenStore(storage_path=os.path.join(tmp_dir, "tokens.json"))
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            store.save(
                OAuthCredential(
                    account_id="account-a",
                    access_token="a",
                    refresh_token="ra",
                    expires_at=expires_at,
                )
            )
            store.save(
                OAuthCredential(
                    account_id="account-b",
                    access_token="b",
                    refresh_token="rb",
                    expires_at=expires_at,
                )
            )

            loaded_a = store.load("account-a")
            loaded_b = store.load("account-b")

        self.assertEqual(loaded_a.access_token, "a")
        self.assertEqual(loaded_b.access_token, "b")

    def test_works_with_credential_loader_unmodified(self):
        # Sprint002의 CredentialLoader(무수정)가 FileTokenStore와도
        # Duck Typing으로 그대로 동작해야 한다.
        from app.providers.upload.credential_loader import get_valid_credential
        from app.providers.upload.file_token_store import FileTokenStore
        from app.providers.upload.mock_oauth_service import MockOAuthService

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = FileTokenStore(storage_path=os.path.join(tmp_dir, "tokens.json"))
            service = MockOAuthService()

            credential = get_valid_credential(service, store, DEFAULT_ACCOUNT_ID)

        self.assertEqual(credential.account_id, DEFAULT_ACCOUNT_ID)


class TestMockOAuthServiceUnaffected(unittest.TestCase):
    """Mock OAuth 영향 없음 - GoogleOAuthService 추가 후에도
    MockOAuthService가 그대로 동작하는지 재확인한다."""

    def test_mock_oauth_service_still_works(self):
        from app.providers.upload.mock_oauth_service import MockOAuthService

        service = MockOAuthService()
        credential = service.authenticate(DEFAULT_ACCOUNT_ID)
        channel = service.fetch_channel_info(credential)

        self.assertEqual(channel.account_id, DEFAULT_ACCOUNT_ID)

    def test_existing_upload_provider_still_works(self):
        from app.providers.upload.mock_upload_provider import MockUploadProvider

        result = MockUploadProvider().upload("output/video.mp4", {"title": "t"})

        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
