"""
Sprint90 - OAuth Manager 이식 (Porting Phase 3).

OneDrive 저장소의 desktop/application/oauth/를 가져오되 Qt를 걷어낸다.
원본 oauth_manager.py와 credential_health.py에는 PySide6 import가
애초에 없다 - Qt에 묶여 있던 것은 oauth_worker.py(QThread) 하나뿐이고,
그것은 "콜러블 하나를 백그라운드에서 돌린다"가 전부라 이미 있는
studio_jobs 패턴이 그대로 대신한다.

가장 중요한 안전 요구사항은 원본 docstring에 적힌 그대로다.

  check_health()  로컬 토큰 파일만 읽는다. Network 호출 없음.
                  화면을 열 때마다 불러도 안전하다.
  verify_now()    실제 Google에 확인한다. 만료면 refresh까지.
                  단 authenticate()는 부르지 않는다 - credential_loader.
                  get_valid_credential()을 그대로 쓰면 저장된 자격이
                  없을 때 브라우저가 저절로 열린다.
  reauthenticate() 브라우저를 연다. 사용자가 버튼을 눌렀을 때만.

이 테스트들이 그 경계를 고정한다.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.providers.upload.oauth_credential import OAuthCredential
from app.providers.upload.oauth_service import OAuthError
from app.services import oauth_health, oauth_manager as manager_module
from app.services.oauth_manager import OAuthManager


def _credential(expires_in_minutes=60, account_id="default"):
    return OAuthCredential(
        account_id=account_id,
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(timezone.utc) + timedelta(
            minutes=expires_in_minutes,
        ),
    )


class _Store:
    def __init__(self, credential=None, raises=None):
        self.credential = credential
        self.raises = raises
        self.saved = []
        self.deleted = []

    def load(self, account_id):
        if self.raises:
            raise self.raises
        return self.credential

    def save(self, credential):
        self.saved.append(credential)
        self.credential = credential

    def delete(self, account_id):
        self.deleted.append(account_id)
        self.credential = None


class _Channel:
    channel_title = "웰빙플랜트"


class _Service:
    """실제 GoogleOAuthService 자리. 어떤 메서드가 불렸는지만 기록한다."""

    def __init__(self, refresh_error=None, fetch_error=None):
        self.calls = []
        self.refresh_error = refresh_error
        self.fetch_error = fetch_error

    def authenticate(self, account_id):
        self.calls.append("authenticate")
        return _credential(account_id=account_id)

    def refresh(self, credential):
        self.calls.append("refresh")
        if self.refresh_error:
            raise self.refresh_error
        return _credential()

    def fetch_channel_info(self, credential):
        self.calls.append("fetch_channel_info")
        if self.fetch_error:
            raise self.fetch_error
        return _Channel()


class TestCredentialHealthPort(unittest.TestCase):
    """원본 분류 규칙이 그대로 살아 있는지."""

    def test_the_status_vocabulary_is_unchanged(self):
        self.assertEqual(
            oauth_health.CREDENTIAL_HEALTH_OPTIONS,
            ["READY", "EXPIRED", "REAUTH_REQUIRED", "INVALID_SCOPE",
             "UNKNOWN"],
        )

    def test_real_google_revocation_strings_map_to_reauth(self):
        """실제 Production QA에서 재현된 문자열이다. 지어낸 패턴이 아니다."""

        for message in ("invalid_grant",
                        "Token has been expired or revoked"):
            with self.subTest(message=message):
                self.assertEqual(
                    oauth_health.classify_error_message(message),
                    oauth_health.REAUTH_REQUIRED,
                )

    def test_meta_graph_strings_map_to_reauth(self):
        for message in ("OAuthException",
                        "Error validating access token"):
            with self.subTest(message=message):
                self.assertEqual(
                    oauth_health.classify_error_message(message),
                    oauth_health.REAUTH_REQUIRED,
                )

    def test_scope_errors_are_distinguished(self):
        self.assertEqual(
            oauth_health.classify_error_message(
                "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
            ),
            oauth_health.INVALID_SCOPE,
        )

    def test_an_empty_message_is_unknown(self):
        self.assertEqual(
            oauth_health.classify_error_message(""), oauth_health.UNKNOWN,
        )

    def test_the_port_imports_no_qt(self):
        """원문 검색은 산문까지 잡는다 - 이 모듈들의 docstring이 "원본에
        PySide6가 없었다"고 설명하고 있어서 문자열 검색으로는 걸린다.
        확인할 것은 실제 import다."""

        import ast

        for module in (oauth_health, manager_module):
            tree = ast.parse(open(module.__file__, encoding="utf-8").read())

            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add(node.module or "")

            for name in imported:
                with self.subTest(module=module.__name__, name=name):
                    self.assertNotIn("PySide", name)
                    self.assertNotIn("PyQt", name)

    def test_the_port_defines_no_qt_classes(self):
        for module in (oauth_health, manager_module):
            for attr in dir(module):
                obj = getattr(module, attr)
                base_names = [
                    b.__name__ for b in getattr(obj, "__mro__", [])
                ] if isinstance(obj, type) else []
                with self.subTest(module=module.__name__, attr=attr):
                    self.assertNotIn("QThread", base_names)
                    self.assertNotIn("QObject", base_names)


class TestCheckHealthNeverTouchesTheNetwork(unittest.TestCase):
    """화면을 열 때마다 불리는 경로다."""

    def test_no_credential_means_reauth_required(self):
        health = OAuthManager(_Service(), _Store(None)).check_health()

        self.assertEqual(health.status, oauth_health.REAUTH_REQUIRED)

    def test_an_expired_credential_reports_the_exact_message(self):
        health = OAuthManager(
            _Service(), _Store(_credential(expires_in_minutes=-1)),
        ).check_health()

        self.assertEqual(health.status, oauth_health.EXPIRED)
        self.assertEqual(
            health.message, "Access Token이 만료되었습니다(자동 갱신 필요).",
        )

    def test_a_valid_credential_is_ready(self):
        health = OAuthManager(_Service(), _Store(_credential())).check_health()

        self.assertEqual(health.status, oauth_health.READY)

    def test_check_health_calls_no_service_method_at_all(self):
        """Network도 브라우저도 건드리지 않는다는 것의 실질."""

        service = _Service()

        OAuthManager(service, _Store(_credential())).check_health()
        OAuthManager(service, _Store(None)).check_health()
        OAuthManager(
            service, _Store(_credential(expires_in_minutes=-1)),
        ).check_health()

        self.assertEqual(service.calls, [])

    def test_a_broken_store_is_unknown_not_a_crash(self):
        health = OAuthManager(
            _Service(), _Store(raises=OSError("디스크 오류")),
        ).check_health()

        self.assertEqual(health.status, oauth_health.UNKNOWN)


class TestVerifyNowNeverOpensABrowser(unittest.TestCase):
    """원본이 credential_loader.get_valid_credential()을 재사용하지 않은
    이유가 이것이다 - 그 함수는 저장된 자격이 없으면 authenticate()를
    자동으로 부른다."""

    def test_no_credential_does_not_authenticate(self):
        service = _Service()

        health = OAuthManager(service, _Store(None)).verify_now()

        self.assertEqual(health.status, oauth_health.REAUTH_REQUIRED)
        self.assertNotIn("authenticate", service.calls)

    def test_an_expired_credential_is_refreshed_not_reauthenticated(self):
        service = _Service()
        store = _Store(_credential(expires_in_minutes=-1))

        health = OAuthManager(service, store).verify_now()

        self.assertIn("refresh", service.calls)
        self.assertNotIn("authenticate", service.calls)
        self.assertEqual(len(store.saved), 1)
        self.assertEqual(health.status, oauth_health.READY)

    def test_a_valid_credential_is_verified_against_the_channel(self):
        service = _Service()

        health = OAuthManager(service, _Store(_credential())).verify_now()

        self.assertEqual(service.calls, ["fetch_channel_info"])
        self.assertIn("웰빙플랜트", health.message)

    def test_a_revoked_token_is_classified_from_the_real_message(self):
        service = _Service(
            refresh_error=OAuthError("invalid_grant: Token has been expired"),
        )

        health = OAuthManager(
            service, _Store(_credential(expires_in_minutes=-1)),
        ).verify_now()

        self.assertEqual(health.status, oauth_health.REAUTH_REQUIRED)


class TestReauthenticateIsTheOnlyBrowserPath(unittest.TestCase):

    def test_it_authenticates_and_saves(self):
        service = _Service()
        store = _Store(None)

        health = OAuthManager(service, store).reauthenticate()

        self.assertEqual(service.calls, ["authenticate"])
        self.assertEqual(len(store.saved), 1)
        self.assertEqual(health.status, oauth_health.READY)

    def test_a_failure_is_reported_not_raised(self):
        service = _Service()
        service.authenticate = lambda account_id: (_ for _ in ()).throw(
            OAuthError("client_secret 파일이 없습니다"),
        )

        health = OAuthManager(service, _Store(None)).reauthenticate()

        self.assertEqual(health.status, oauth_health.UNKNOWN)
        self.assertIn("client_secret", health.message)


class TestLogout(unittest.TestCase):
    """Sprint90 추가. 원본 OAuthManager에는 없지만 FileTokenStore.delete()가
    이미 있고 RealYouTubeRuntime.revoke()가 그것을 쓴다 - 새 로직이
    아니라 이미 있는 것을 엮는다."""

    def test_logout_deletes_the_stored_credential(self):
        store = _Store(_credential())

        health = OAuthManager(_Service(), store).logout()

        self.assertEqual(store.deleted, ["default"])
        self.assertEqual(health.status, oauth_health.REAUTH_REQUIRED)

    def test_logout_touches_no_service_method(self):
        service = _Service()

        OAuthManager(service, _Store(_credential())).logout()

        self.assertEqual(service.calls, [])

    def test_logging_out_twice_is_not_an_error(self):
        store = _Store(None)

        OAuthManager(_Service(), store).logout()
        OAuthManager(_Service(), store).logout()

        self.assertEqual(len(store.deleted), 2)


class TestDefaultManagerConstruction(unittest.TestCase):
    """자격증명 파일이 없어도 만들어지기만은 해야 한다 - 없다는 것을
    화면이 보여줘야 하는데, 만드는 순간 터지면 그것도 못 한다."""

    def test_building_without_any_credential_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "YOUTUBE_OAUTH_CLIENT_SECRET_PATH":
                    os.path.join(tmp, "nope.json"),
                "YOUTUBE_OAUTH_TOKEN_STORE_PATH":
                    os.path.join(tmp, "tokens.json"),
            }
            old = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                manager = manager_module.build_default_oauth_manager()
                health = manager.check_health()
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

        self.assertEqual(health.status, oauth_health.REAUTH_REQUIRED)

    def test_the_paths_come_from_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_path = os.path.join(tmp, "custom_tokens.json")
            os.environ["YOUTUBE_OAUTH_TOKEN_STORE_PATH"] = token_path
            try:
                manager = manager_module.build_default_oauth_manager()
            finally:
                os.environ.pop("YOUTUBE_OAUTH_TOKEN_STORE_PATH", None)

        self.assertEqual(manager.token_store.storage_path, token_path)


if __name__ == "__main__":
    unittest.main()


class TestOAuthEndpoints(unittest.TestCase):
    """Sprint90 - HTTP 4개. Upload Runtime은 아직 연결하지 않는다."""

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.services import studio_jobs

        self.client = TestClient(app)
        studio_jobs.reset()
        self.addCleanup(studio_jobs.reset)

    def test_status_is_readable_without_any_credential(self):
        response = self.client.get("/studio/api/oauth/status")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            response.json()["status"], oauth_health.CREDENTIAL_HEALTH_OPTIONS,
        )

    def test_status_reports_where_it_is_looking(self):
        """자격증명이 없을 때 어디에 두면 되는지가 드러나야 한다."""

        data = self.client.get("/studio/api/oauth/status").json()

        self.assertIn("token_store_path", data)
        self.assertIn("client_secret_path", data)

    def test_status_never_opens_a_browser(self):
        """GET 한 번으로 브라우저가 열리면 안 된다."""

        from unittest.mock import patch

        with patch("webbrowser.open") as opened, \
                patch("app.providers.upload.google_oauth_service"
                      ".InstalledAppFlow") as flow:
            self.client.get("/studio/api/oauth/status")

        opened.assert_not_called()
        flow.from_client_secrets_file.assert_not_called()

    def test_the_three_actions_are_accepted(self):
        from unittest.mock import patch

        from app.services import studio_jobs

        for action in ("login", "refresh", "logout"):
            with self.subTest(action=action):
                with patch.object(
                    studio_jobs, "start_oauth", return_value="job1",
                ):
                    response = self.client.post(
                        f"/studio/api/oauth/{action}",
                    )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["job_id"], "job1")

    def test_an_unknown_action_is_rejected(self):
        response = self.client.post("/studio/api/oauth/wipe_everything")

        self.assertEqual(response.status_code, 400)

    def test_the_oauth_endpoints_do_not_upload_anything(self):
        """Sprint90에서는 "업로드 엔드포인트가 하나도 없어야 한다"였다.
        Sprint92가 승인된 프로젝트를 올리는 경로를 붙였으므로 그 문장은
        더 이상 사실이 아니다.

        지켜야 할 경계는 그대로다 - OAuth 동작 셋은 인증만 다루고
        업로드를 시작하지 않는다."""

        from app.main import app

        paths = list(app.openapi()["paths"])
        oauth_paths = [p for p in paths if "oauth" in p.lower()]

        self.assertTrue(oauth_paths)
        for path in oauth_paths:
            with self.subTest(path=path):
                self.assertNotIn("upload", path.lower())
