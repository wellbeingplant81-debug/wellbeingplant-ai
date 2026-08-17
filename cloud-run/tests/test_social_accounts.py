"""
Sprint217 - SNS 계정 연동 (Epic 61).

이 스위트가 지키는 것은 "로그인이 된다"가 아니다. 실제 로그인은 사람이
브라우저에서 하는 일이고 진짜 Meta/TikTok 앱이 있어야 한다. 여기서
지키는 것은 그 경계 안쪽의 약속들이다.

    1. 눌러도 아무 반응 없는 경로가 없다      실패는 반드시 말이 된다
    2. 없는 것을 연결됐다고 하지 않는다
    3. 설정 필요와 연결 안 됨을 가른다        전자는 눌러도 안 된다
    4. state를 확인한다                       인가 코드 주입을 버린다
    5. PKCE는 실제로 S256이다
    6. 토큰이 평문으로 디스크에 남지 않는다
    7. 자격증명 자리가 묶인 프로그램에서도 있다

특히 7번이 이 Epic의 출발점이다 - 바탕화면 exe에서 [Google 로그인]을
눌러도 브라우저가 열리지 않은 실제 원인이 상대 경로였다.
"""

import base64
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.providers.upload import oauth_loopback
from app.providers.upload.oauth_credential import OAuthCredential
from app.providers.upload.oauth_service import OAuthError
from app.providers.upload.tiktok_oauth_service import (
    TikTokOAuthService, challenge_for, new_verifier,
)
from app.services import oauth_health, secret_box, social_accounts as social

_TIKTOK = "app.providers.upload.tiktok_oauth_service"


def _credential(account_id="default", expires_in=3600):
    return OAuthCredential(
        account_id=account_id,
        access_token="at",
        refresh_token="rt",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


# ══ 1. 자격증명이 어디 있는가 ════════════════════════════════════════

class TheCredentialHomeTest(unittest.TestCase):
    """묶인 프로그램에서도 자리가 있어야 한다."""

    def test_the_environment_variable_always_wins(self):
        """테스트와 운영이 쓰는 문이다. 막으면 안 된다."""

        from app.services import credential_paths

        with tempfile.TemporaryDirectory() as tmp:
            given = os.path.join(tmp, "given.json")

            with patch.dict(os.environ, {"X_SECRET_PATH": given}):
                self.assertEqual(
                    credential_paths.resolve("X_SECRET_PATH", "any.json"),
                    given)

    def test_a_frozen_program_looks_under_the_user_home(self):
        """
        여기가 이 Epic의 출발점이다.

        예전 기본값은 상대 경로 "credentials/client_secret.json"이었다.
        묶은 프로그램은 사람이 두 번 누른 자리(바탕화면)에서 켜지므로
        그 파일을 영원히 못 찾았고, 그래서 브라우저가 열리지 않았다.
        """

        from app import runtime_paths
        from app.services import credential_paths

        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {runtime_paths.HOME_ENV: home},
                            clear=False):
                os.environ.pop("Y_SECRET_PATH", None)

                # 저장소의 credentials/ 를 못 보게 한다 - 묶인 프로그램의
                # 상황을 그대로 재현한다.
                with patch.object(credential_paths, "repo_dir",
                                  return_value=os.path.join(home, "nope")):
                    where = credential_paths.resolve(
                        "Y_SECRET_PATH", "client_secret.json")

        self.assertTrue(where.startswith(home), where)
        self.assertTrue(os.path.isabs(where), where)

    def test_the_path_is_returned_even_when_the_file_is_missing(self):
        """
        없어도 경로를 돌려준다.

        화면이 그 경로를 보여 주어야 사람이 어디에 파일을 두면 되는지
        안다 - 예전에는 'credentials/client_secret.json'이라는 상대
        경로만 보였고, 받은 사람에게 그것은 아무 자리도 아니었다.
        """

        from app.services import credential_paths

        with tempfile.TemporaryDirectory() as home:
            from app import runtime_paths

            with patch.dict(os.environ, {runtime_paths.HOME_ENV: home}):
                os.environ.pop("Z_SECRET_PATH", None)

                with patch.object(credential_paths, "repo_dir",
                                  return_value=os.path.join(home, "nope")):
                    where = credential_paths.resolve(
                        "Z_SECRET_PATH", "missing.json")

        self.assertFalse(os.path.exists(where))
        self.assertIn("missing.json", where)


class TheMissingClientSecretSpeaksPlainlyTest(unittest.TestCase):
    """"알 수 없음 / No such file or directory"는 사람이 쓸 수 없는 글이다."""

    def test_it_names_the_place_to_put_the_file(self):
        from app.providers.upload.google_oauth_service import (
            GoogleOAuthService,
        )

        with tempfile.TemporaryDirectory() as tmp:
            nowhere = os.path.join(tmp, "client_secret.json")
            service = GoogleOAuthService(client_secret_path=nowhere)

            with self.assertRaises(OAuthError) as caught:
                service.authenticate("default")

        said = str(caught.exception)

        self.assertIn(nowhere, said)
        self.assertIn("데스크톱", said)
        # 브라우저를 열지 못한 이유가 적혀 있어야 한다.
        self.assertIn("브라우저", said)

    def test_it_never_reaches_the_browser(self):
        """파일이 없으면 브라우저를 열 시도조차 하지 않는다."""

        from app.providers.upload import google_oauth_service

        with tempfile.TemporaryDirectory() as tmp:
            service = google_oauth_service.GoogleOAuthService(
                client_secret_path=os.path.join(tmp, "nope.json"))

            with patch.object(google_oauth_service, "InstalledAppFlow") as flow:
                with self.assertRaises(OAuthError):
                    service.authenticate("default")

        flow.from_client_secrets_file.assert_not_called()


# ══ 2. 공통 구조 ═════════════════════════════════════════════════════

class TheCommonInterfaceTest(unittest.TestCase):
    """셋이 같은 다섯 개를 갖는다."""

    def setUp(self):
        self.manager = social.build_default_social_auth_manager()

    def test_all_three_platforms_are_offered(self):
        self.assertEqual(sorted(self.manager.platforms()),
                         sorted([social.YOUTUBE, social.INSTAGRAM,
                                 social.TIKTOK]))

    def test_every_provider_answers_the_same_five_calls(self):
        for platform in self.manager.platforms():
            provider = self.manager.provider(platform)

            for name in ("login", "logout", "is_authenticated",
                         "get_account", "refresh_token"):
                with self.subTest(platform=platform, call=name):
                    self.assertTrue(callable(getattr(provider, name, None)))

    def test_an_unknown_platform_raises_instead_of_guessing(self):
        with self.assertRaises(KeyError):
            self.manager.provider("facebook")

    def test_listing_accounts_opens_no_browser_and_touches_no_network(self):
        """화면을 열 때마다 불리는 자리다. 브라우저가 저절로 열리면 결함이다."""

        import webbrowser

        import requests

        with patch.object(webbrowser, "open") as opened, \
                patch.object(requests, "get") as got, \
                patch.object(requests, "post") as posted:
            self.manager.accounts()

        opened.assert_not_called()
        got.assert_not_called()
        posted.assert_not_called()


class TheStateIsNotFakedTest(unittest.TestCase):
    """없는 것을 연결됐다고 하지 않는다."""

    def _provider(self, platform, health_status, token=None, missing=()):
        manager = MagicMock()
        manager.account_id = "default"
        manager.token_store.load.return_value = token
        manager.check_health.return_value = oauth_health.CredentialHealth(
            health_status, "말", 0.0)

        klass = {
            social.YOUTUBE: social.YouTubeAuthProvider,
            social.INSTAGRAM: social.InstagramAuthProvider,
            social.TIKTOK: social.TikTokAuthProvider,
        }[platform]

        provider = klass(manager)
        provider.missing_setup = lambda: list(missing)

        return provider

    def test_no_token_is_never_connected(self):
        for status in oauth_health.CREDENTIAL_HEALTH_OPTIONS:
            with self.subTest(status=status):
                provider = self._provider(social.TIKTOK, status, token=None)

                self.assertFalse(provider.is_authenticated())

    def test_only_ready_counts_as_connected(self):
        for status in oauth_health.CREDENTIAL_HEALTH_OPTIONS:
            with self.subTest(status=status):
                account = self._provider(
                    social.TIKTOK, status, token=_credential()).get_account()

                self.assertEqual(account.connected,
                                 status == oauth_health.READY)

    def test_missing_setup_is_not_the_same_as_needs_login(self):
        """
        둘을 같은 말로 적으면 사람은 단추를 누르며 시간을 버린다.

        연결 안 됨 = 누르면 된다. 설정 필요 = 눌러도 안 된다, 바깥에서
        먼저 할 일이 있다.
        """

        needs_setup = self._provider(
            social.TIKTOK, oauth_health.REAUTH_REQUIRED,
            token=None, missing=["TIKTOK_CLIENT_KEY"]).get_account()

        needs_login = self._provider(
            social.TIKTOK, oauth_health.REAUTH_REQUIRED,
            token=None, missing=[]).get_account()

        self.assertEqual(needs_setup.state, social.NEEDS_SETUP)
        self.assertEqual(needs_login.state, social.NEEDS_LOGIN)
        self.assertNotEqual(needs_setup.state, needs_login.state)
        self.assertIn("TIKTOK_CLIENT_KEY", needs_setup.missing_setup)
        self.assertTrue(needs_setup.setup_hint)

    def test_an_already_connected_account_survives_missing_setup(self):
        """설정이 사라졌다고 이미 받아 둔 로그인을 부정하지 않는다."""

        account = self._provider(
            social.TIKTOK, oauth_health.READY, token=_credential(),
            missing=["TIKTOK_CLIENT_KEY"]).get_account()

        self.assertTrue(account.connected)

    def test_a_failed_login_reports_the_reason_not_silence(self):
        """
        이 Epic의 이름이 붙은 결함이다 - "눌러도 아무 반응 없음".

        reauthenticate()가 실패를 health로 돌려주는 경로가 있고, 그
        문장이 사람에게 닿는 유일한 단서다. 버리지 않는다.
        """

        manager = MagicMock()
        manager.account_id = "default"
        manager.token_store.load.return_value = None
        manager.reauthenticate.return_value = oauth_health.CredentialHealth(
            oauth_health.UNKNOWN, "자격증명 파일이 없습니다", 0.0)
        manager.check_health.return_value = oauth_health.CredentialHealth(
            oauth_health.REAUTH_REQUIRED, "없음", 0.0)

        provider = social.TikTokAuthProvider(manager)
        provider.missing_setup = lambda: []

        account = provider.login()

        self.assertFalse(account.connected)
        self.assertIn("자격증명 파일이 없습니다", account.message)

    def test_logout_leaves_it_disconnected(self):
        manager = MagicMock()
        manager.account_id = "default"
        manager.token_store.load.return_value = None
        manager.check_health.return_value = oauth_health.CredentialHealth(
            oauth_health.REAUTH_REQUIRED, "로그아웃되었습니다.", 0.0)

        provider = social.TikTokAuthProvider(manager)
        provider.missing_setup = lambda: []

        account = provider.logout()

        manager.logout.assert_called_once()
        self.assertFalse(account.connected)

    def test_refresh_picks_up_the_account_name_it_actually_fetched(self):
        """이름은 실제로 받아 온 것만 적는다 - 지어내지 않는다."""

        manager = MagicMock()
        manager.account_id = "default"
        manager.token_store.load.return_value = _credential()
        manager.verify_now.return_value = oauth_health.CredentialHealth(
            oauth_health.READY, "웰빙플랜트lab 채널에 연결됨.", 0.0)

        provider = social.YouTubeAuthProvider(manager)
        provider.missing_setup = lambda: []

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                "SOCIAL_ACCOUNT_NAMES_PATH": os.path.join(tmp, "n.json"),
            }):
                account = provider.refresh_token()

        self.assertTrue(account.connected)
        self.assertEqual(account.account_name, "웰빙플랜트lab")


class TheAccountNameSurvivesARestartTest(unittest.TestCase):
    """
    화면이 "연결됨"이라고만 말하고 어느 계정인지 모르면, 채널을 여러 개
    쓰는 사람에게는 그것이 곧 위험이다. 한 번 받아 온 이름은 적어 둔다.

    이름은 비밀이 아니다 - 공개된 채널 이름이고 토큰과 달리 감쌀 것이
    없다. "실제로 받아 온 것만 적는다"는 규칙은 그대로다.
    """

    def _provider(self, health_status, message, token=_credential()):
        manager = MagicMock()
        manager.account_id = "default"
        manager.token_store.load.return_value = token
        manager.verify_now.return_value = oauth_health.CredentialHealth(
            health_status, message, 0.0)
        manager.check_health.return_value = oauth_health.CredentialHealth(
            health_status, message, 0.0)

        provider = social.YouTubeAuthProvider(manager)
        provider.missing_setup = lambda: []

        return provider

    def setUp(self):
        # 같은 프로세스의 메모리 캐시가 테스트끼리 새는 것을 막는다.
        social.SocialAuthProvider._cache.clear()
        self.addCleanup(social.SocialAuthProvider._cache.clear)

    def test_a_later_health_check_still_knows_the_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            where = os.path.join(tmp, "names.json")

            with patch.dict(os.environ, {"SOCIAL_ACCOUNT_NAMES_PATH": where}):
                self._provider(oauth_health.READY,
                               "웰빙플랜트lab 채널에 연결됨.").refresh_token()

                # 새로 켠 것처럼 캐시를 비운다.
                social.SocialAuthProvider._cache.clear()

                account = self._provider(
                    oauth_health.READY, "정상 연결됨.").get_account()

        self.assertEqual(account.account_name, "웰빙플랜트lab")

    def test_a_disconnected_account_shows_no_name(self):
        """끊긴 연결에 지난 이름을 붙여 두지 않는다."""

        with tempfile.TemporaryDirectory() as tmp:
            where = os.path.join(tmp, "names.json")

            with patch.dict(os.environ, {"SOCIAL_ACCOUNT_NAMES_PATH": where}):
                self._provider(oauth_health.READY,
                               "웰빙플랜트lab 채널에 연결됨.").refresh_token()

                account = self._provider(
                    oauth_health.REAUTH_REQUIRED, "로그인 필요",
                    token=None).get_account()

        self.assertEqual(account.account_name, "")

    def test_logout_forgets_the_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            where = os.path.join(tmp, "names.json")

            with patch.dict(os.environ, {"SOCIAL_ACCOUNT_NAMES_PATH": where}):
                self._provider(oauth_health.READY,
                               "웰빙플랜트lab 채널에 연결됨.").refresh_token()

                provider = self._provider(
                    oauth_health.REAUTH_REQUIRED, "로그아웃되었습니다.",
                    token=None)
                provider.logout()

                self.assertEqual(json.load(open(where, encoding="utf-8")), {})

    def test_no_name_file_is_not_a_failure(self):
        """이름은 보조 정보다. 없어도 화면은 그대로 돈다."""

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                "SOCIAL_ACCOUNT_NAMES_PATH": os.path.join(tmp, "nope.json"),
            }):
                account = self._provider(
                    oauth_health.READY, "정상 연결됨.").get_account()

        self.assertTrue(account.connected)
        self.assertEqual(account.account_name, "")

    def test_a_broken_name_file_is_not_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            where = os.path.join(tmp, "names.json")
            open(where, "w", encoding="utf-8").write("{ 망가진 json")

            with patch.dict(os.environ, {"SOCIAL_ACCOUNT_NAMES_PATH": where}):
                account = self._provider(
                    oauth_health.READY, "정상 연결됨.").get_account()

        self.assertTrue(account.connected)
        self.assertEqual(account.account_name, "")

    def test_the_name_file_holds_no_token(self):
        """이 파일에는 이름만 들어간다."""

        with tempfile.TemporaryDirectory() as tmp:
            where = os.path.join(tmp, "names.json")

            with patch.dict(os.environ, {"SOCIAL_ACCOUNT_NAMES_PATH": where}):
                self._provider(oauth_health.READY,
                               "웰빙플랜트lab 채널에 연결됨.").refresh_token()

            raw = open(where, encoding="utf-8").read()

        self.assertIn("웰빙플랜트lab", raw)
        for word in ("access_token", "refresh_token", "client_secret"):
            with self.subTest(word=word):
                self.assertNotIn(word, raw)


class TheFailureSpeaksKoreanTest(unittest.TestCase):
    """
    삼키지 않는 것으로는 부족하다.

    바탕화면 exe에서 실제로 이런 것이 떴다.

        Google OAuth authentication failed for account default:
        (mismatching_state) CSRF Warning! State not equal in request
        and response.

    받은 사람이 저 글로 할 수 있는 일이 없다.
    """

    def test_the_known_failures_become_plain_korean(self):
        cases = {
            "(mismatching_state) CSRF Warning!": "다시 시도",
            "error=access_denied": "동의하지",
            "[Errno 2] No such file or directory: 'x'": "자격증명 파일",
            "invalid_grant: Token has been revoked": "다시 로그인",
            "invalid_client: Unauthorized": "client_secret",
            "OSError: [WinError 10048] Address already in use": "포트",
            "Max retries exceeded with url": "인터넷",
        }

        for said, expected in cases.items():
            with self.subTest(said=said):
                self.assertIn(expected, social.plain_message(said))

    def test_the_original_is_kept_for_us(self):
        """우리가 알아볼 단서는 버리지 않는다."""

        said = "(mismatching_state) CSRF Warning!"

        self.assertIn(said, social.plain_message(said))

    def test_an_unknown_failure_is_left_alone(self):
        """모르는 것을 아는 척 바꾸지 않는다."""

        said = "무슨 일인지 우리도 모르는 문장"

        self.assertEqual(social.plain_message(said), said)

    def test_empty_stays_empty(self):
        self.assertEqual(social.plain_message(None), "")
        self.assertEqual(social.plain_message("  "), "")

    def test_a_success_message_is_not_mangled(self):
        """이름을 뽑아내는 쪽이 이 문장을 읽는다 - 손대면 안 된다."""

        said = "웰빙플랜트lab 채널에 연결됨."

        self.assertEqual(social.plain_message(said), said)


# ══ 3. state 검증 ════════════════════════════════════════════════════

class TheStateGuardTest(unittest.TestCase):
    """
    state를 확인하지 않으면 인가 코드 주입이 뚫린다.

    콜백 서버는 127.0.0.1의 정해진 포트에서 아무 요청이나 받는다. 그
    사이에 다른 탭이 /callback?code=<공격자코드> 를 한 번 부르면, 우리는
    그것을 토큰으로 바꾸어 **공격자 계정을 이 사람 계정으로 저장**한다.
    """

    def test_two_states_are_never_the_same(self):
        made = {oauth_loopback.new_state() for _ in range(200)}

        self.assertEqual(len(made), 200)

    def test_a_state_is_long_enough_to_not_be_guessed(self):
        self.assertGreaterEqual(len(oauth_loopback.new_state()), 32)

    def _server_yielding(self, code, state):
        def factory(*args, **kwargs):
            instance = MagicMock()
            instance.received_code = None
            instance.received_error = None
            instance.received_state = None

            def handle():
                instance.received_code = code
                instance.received_state = state

            instance.handle_request.side_effect = handle
            return instance

        return factory

    def test_a_mismatched_state_throws_the_code_away(self):
        with patch.object(oauth_loopback, "HTTPServer",
                          side_effect=self._server_yielding(
                              "attacker-code", "not-our-state")), \
                patch.object(oauth_loopback, "open_browser"):
            with self.assertRaises(OAuthError) as caught:
                oauth_loopback.capture_code(
                    "https://example.test/auth", "127.0.0.1", 8599,
                    expected_state="ours", timeout_seconds=0.05)

        self.assertIn("state", str(caught.exception))

    def test_a_missing_state_throws_the_code_away(self):
        """state가 아예 없는 콜백도 버린다 - 그것이 주입의 모양이다."""

        with patch.object(oauth_loopback, "HTTPServer",
                          side_effect=self._server_yielding(
                              "attacker-code", None)), \
                patch.object(oauth_loopback, "open_browser"):
            with self.assertRaises(OAuthError):
                oauth_loopback.capture_code(
                    "https://example.test/auth", "127.0.0.1", 8599,
                    expected_state="ours", timeout_seconds=0.05)

    def test_a_matching_state_is_accepted(self):
        with patch.object(oauth_loopback, "HTTPServer",
                          side_effect=self._server_yielding(
                              "our-code", "ours")), \
                patch.object(oauth_loopback, "open_browser"):
            got = oauth_loopback.capture_code(
                "https://example.test/auth", "127.0.0.1", 8599,
                expected_state="ours", timeout_seconds=0.05)

        self.assertEqual(got, "our-code")

    def test_instagram_now_sends_a_state(self):
        """예전에는 authorize URL에 state가 아예 없었다."""

        from app.providers.upload.instagram_oauth_service import (
            InstagramOAuthService,
        )
        import app.providers.upload.instagram_oauth_service as module

        service = InstagramOAuthService(
            client_id="id", client_secret="secret",
            redirect_uri="http://localhost:8551/callback",
            callback_timeout_seconds=0.05)

        seen = {}

        def remember(url):
            seen["url"] = url
            return True

        def factory(*args, **kwargs):
            instance = MagicMock()
            instance.received_code = None
            instance.received_error = None
            instance.received_state = None

            def handle():
                instance.received_code = "code"
                instance.received_state = instance.expected_state

            instance.handle_request.side_effect = handle
            return instance

        with patch.object(module, "HTTPServer", side_effect=factory), \
                patch.object(module.webbrowser, "open", side_effect=remember):
            service._authorize_and_capture_code()

        self.assertIn("state=", seen["url"])


class TheBrowserFailureIsNotSilentTest(unittest.TestCase):
    """
    webbrowser.open()은 실패를 예외로 던지지 않고 False를 돌려준다.

    그 False를 버리면 브라우저가 열리지도 않은 채 콜백을 5분 기다린다 -
    사람에게는 정확히 "눌러도 아무 반응 없음"이다.
    """

    def test_a_refused_browser_becomes_an_oauth_error(self):
        import webbrowser

        with patch.object(webbrowser, "open", return_value=False):
            with self.assertRaises(OAuthError) as caught:
                oauth_loopback.open_browser("https://example.test/auth")

        self.assertIn("브라우저", str(caught.exception))
        # 사람이 직접 열 수 있게 주소를 함께 준다.
        self.assertIn("https://example.test/auth", str(caught.exception))

    def test_a_raising_browser_becomes_an_oauth_error(self):
        import webbrowser

        with patch.object(webbrowser, "open", side_effect=RuntimeError("nope")):
            with self.assertRaises(OAuthError):
                oauth_loopback.open_browser("https://example.test/auth")

    def test_a_busy_port_says_which_port(self):
        with patch.object(oauth_loopback, "HTTPServer",
                          side_effect=OSError("Address already in use")):
            with self.assertRaises(OAuthError) as caught:
                oauth_loopback.capture_code(
                    "https://example.test/auth", "127.0.0.1", 8599,
                    expected_state="ours", timeout_seconds=0.05)

        self.assertIn("8599", str(caught.exception))

    def test_a_timeout_says_it_timed_out(self):
        def factory(*args, **kwargs):
            instance = MagicMock()
            instance.received_code = None
            instance.received_error = None
            instance.handle_request.side_effect = lambda: None
            return instance

        with patch.object(oauth_loopback, "HTTPServer", side_effect=factory), \
                patch.object(oauth_loopback, "open_browser"):
            with self.assertRaises(OAuthError) as caught:
                oauth_loopback.capture_code(
                    "https://example.test/auth", "127.0.0.1", 8599,
                    expected_state="ours", timeout_seconds=0.05)

        self.assertIn("제한 시간", str(caught.exception))

    def test_a_denied_login_says_it_was_denied(self):
        # 거부는 콜백 요청과 함께 도착한다 - 서버를 만드는 시점에
        # 미리 얹어 두면 capture_code가 초기화하면서 지운다(실제
        # 서버에서는 그 초기화가 옳다). 실제 흐름 그대로 재현한다.
        def factory(*args, **kwargs):
            instance = MagicMock()
            instance.received_code = None
            instance.received_error = None

            def handle():
                instance.received_error = "access_denied"

            instance.handle_request.side_effect = handle
            return instance

        with patch.object(oauth_loopback, "HTTPServer", side_effect=factory), \
                patch.object(oauth_loopback, "open_browser"):
            with self.assertRaises(OAuthError) as caught:
                oauth_loopback.capture_code(
                    "https://example.test/auth", "127.0.0.1", 8599,
                    expected_state="ours", timeout_seconds=0.05)

        self.assertIn("거부", str(caught.exception))


# ══ 4. TikTok PKCE ═══════════════════════════════════════════════════

class TheTikTokPkceTest(unittest.TestCase):
    """
    데스크톱 프로그램의 client_secret은 비밀이 될 수 없다 - exe를 받은
    사람은 누구나 꺼낸다. PKCE가 그 구멍을 막는다.
    """

    def test_the_verifier_is_within_the_rfc_length(self):
        for _ in range(20):
            self.assertTrue(43 <= len(new_verifier()) <= 128)

    def test_two_verifiers_are_never_the_same(self):
        self.assertEqual(len({new_verifier() for _ in range(200)}), 200)

    def test_the_challenge_is_really_s256(self):
        verifier = "abc123-_~test"

        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")

        self.assertEqual(challenge_for(verifier), expected)

    def test_the_challenge_carries_no_padding(self):
        self.assertNotIn("=", challenge_for(new_verifier()))

    def test_the_challenge_is_not_the_verifier(self):
        """plain 방식이 아니다 - 가로채면 그대로 쓸 수 있게 되면 안 된다."""

        verifier = new_verifier()

        self.assertNotEqual(challenge_for(verifier), verifier)

    def test_authorize_sends_the_challenge_and_token_sends_the_verifier(self):
        service = TikTokOAuthService(
            client_key="key", client_secret="secret",
            redirect_uri="http://127.0.0.1:8562/callback",
            callback_timeout_seconds=0.05)

        seen = {}

        def capture(auth_url, **kwargs):
            seen["url"] = auth_url
            seen["state"] = kwargs["expected_state"]
            return "code-123"

        with patch.object(oauth_loopback, "capture_code", side_effect=capture), \
                patch(f"{_TIKTOK}.requests.post") as posted:
            posted.return_value = MagicMock(
                status_code=200,
                json=lambda: {"access_token": "at", "refresh_token": "rt",
                              "expires_in": 3600})

            service.authenticate("default")

        self.assertIn("code_challenge=", seen["url"])
        self.assertIn("code_challenge_method=S256", seen["url"])
        self.assertIn(f"state={seen['state']}", seen["url"])
        # verifier는 authorize에 실리지 않는다 - 그것이 PKCE의 요점이다.
        self.assertNotIn("code_verifier", seen["url"])

        form = posted.call_args.kwargs["data"]

        self.assertIn("code_verifier", form)
        self.assertEqual(challenge_for(form["code_verifier"]),
                         _challenge_in(seen["url"]))

    def test_it_uses_the_real_tiktok_endpoints(self):
        """추측하지 않았다는 것을 URL 문자열로 증명한다."""

        from app.providers.upload import tiktok_oauth_service as t

        self.assertEqual(t.AUTHORIZE_URL,
                         "https://www.tiktok.com/v2/auth/authorize/")
        self.assertEqual(t.TOKEN_URL,
                         "https://open.tiktokapis.com/v2/oauth/token/")
        self.assertEqual(t.USER_INFO_URL,
                         "https://open.tiktokapis.com/v2/user/info/")


def _challenge_in(url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query)["code_challenge"][0]


class TheTikTokSetupIsNotInventedTest(unittest.TestCase):
    """앱 설정이 없으면 지어내지 않는다."""

    def test_it_names_what_is_missing(self):
        service = TikTokOAuthService(client_key="", client_secret="")

        self.assertEqual(sorted(service.missing_setup()),
                         ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"])

    def test_login_without_setup_opens_no_browser(self):
        service = TikTokOAuthService(client_key="", client_secret="")

        with patch.object(oauth_loopback, "capture_code") as captured:
            with self.assertRaises(OAuthError) as caught:
                service.authenticate("default")

        captured.assert_not_called()
        self.assertIn("TIKTOK_CLIENT_KEY", str(caught.exception))
        self.assertIn("Redirect URI", str(caught.exception))

    def test_nothing_is_hardcoded_as_a_credential(self):
        from app.providers.upload import tiktok_oauth_service as t

        service = t.build_default_tiktok_oauth_service()

        # 환경에 값이 없으면 빈 문자열이다 - 소스에 박힌 열쇠가 없다.
        if not os.environ.get("TIKTOK_CLIENT_KEY"):
            self.assertEqual(service.client_key, "")
        if not os.environ.get("TIKTOK_CLIENT_SECRET"):
            self.assertEqual(service.client_secret, "")


class TheTikTokTokenExchangeTest(unittest.TestCase):

    def _service(self):
        return TikTokOAuthService(
            client_key="key", client_secret="secret",
            callback_timeout_seconds=0.05)

    def test_a_successful_exchange_keeps_both_tokens(self):
        with patch(f"{_TIKTOK}.requests.post") as posted:
            posted.return_value = MagicMock(
                status_code=200,
                json=lambda: {"access_token": "at-1", "refresh_token": "rt-1",
                              "expires_in": 86400})

            with patch.object(oauth_loopback, "capture_code",
                              return_value="code"):
                credential = self._service().authenticate("default")

        self.assertEqual(credential.access_token, "at-1")
        self.assertEqual(credential.refresh_token, "rt-1")
        self.assertGreater(credential.expires_at, datetime.now(timezone.utc))

    def test_an_error_body_with_status_200_is_still_a_failure(self):
        """TikTok v2는 200으로도 error를 담아 보낸다."""

        with patch(f"{_TIKTOK}.requests.post") as posted:
            posted.return_value = MagicMock(
                status_code=200,
                json=lambda: {"error": "invalid_grant",
                              "error_description": "코드가 만료되었습니다"})

            with patch.object(oauth_loopback, "capture_code",
                              return_value="code"):
                with self.assertRaises(OAuthError) as caught:
                    self._service().authenticate("default")

        self.assertIn("만료", str(caught.exception))

    def test_a_network_error_becomes_an_oauth_error(self):
        with patch(f"{_TIKTOK}.requests.post",
                   side_effect=OSError("연결 실패")):
            with patch.object(oauth_loopback, "capture_code",
                              return_value="code"):
                with self.assertRaises(OAuthError) as caught:
                    self._service().authenticate("default")

        self.assertIn("네트워크", str(caught.exception))

    def test_refresh_sends_the_refresh_token(self):
        with patch(f"{_TIKTOK}.requests.post") as posted:
            posted.return_value = MagicMock(
                status_code=200,
                json=lambda: {"access_token": "at-2", "expires_in": 86400})

            refreshed = self._service().refresh(_credential())

        form = posted.call_args.kwargs["data"]

        self.assertEqual(form["grant_type"], "refresh_token")
        self.assertEqual(form["refresh_token"], "rt")
        self.assertEqual(refreshed.access_token, "at-2")
        # 새 refresh_token을 안 주면 있던 것을 지키지 않고 버리면
        # 다음 갱신이 불가능해진다.
        self.assertEqual(refreshed.refresh_token, "rt")

    def test_the_same_redirect_uri_goes_to_both_calls(self):
        """
        고전적인 결함 자리다.

        authorize에 실은 redirect_uri와 토큰 교환에 실은 것이 한 글자라도
        다르면 플랫폼이 invalid_grant로 거절한다. 그때 나는 문장은
        "코드가 유효하지 않다"라서, 원인이 URI 불일치라는 것을 알아낼
        단서가 없다 - 한 곳에서 나온 같은 값이어야 한다.
        """

        given = "http://127.0.0.1:8562/callback"
        service = TikTokOAuthService(
            client_key="key", client_secret="secret", redirect_uri=given,
            callback_timeout_seconds=0.05)

        seen = {}

        def capture(auth_url, **kwargs):
            seen["url"] = auth_url
            seen["port"] = kwargs["port"]
            seen["host"] = kwargs["host"]
            return "code-123"

        with patch.object(oauth_loopback, "capture_code", side_effect=capture), \
                patch(f"{_TIKTOK}.requests.post") as posted:
            posted.return_value = MagicMock(
                status_code=200,
                json=lambda: {"access_token": "at", "expires_in": 1})

            service.authenticate("default")

        from urllib.parse import parse_qs, quote, urlparse

        in_authorize = parse_qs(urlparse(seen["url"]).query)["redirect_uri"][0]
        in_token = posted.call_args.kwargs["data"]["redirect_uri"]

        self.assertEqual(in_authorize, given)
        self.assertEqual(in_token, given)
        # 콜백 서버도 그 URI가 가리키는 자리에 떠야 한다 - 다른 포트에
        # 뜨면 응답이 아무도 안 듣는 자리로 날아간다.
        self.assertEqual(seen["host"], "127.0.0.1")
        self.assertEqual(seen["port"], 8562)
        self.assertIn(quote(given, safe=""), seen["url"])

    def test_a_redirect_uri_without_a_port_still_binds_somewhere_sane(self):
        """포트가 없는 URI를 줘도 80으로 떨어지지 않는다."""

        service = TikTokOAuthService(
            client_key="key", client_secret="secret",
            redirect_uri="https://example.test/callback",
            callback_timeout_seconds=0.05)

        seen = {}

        def capture(auth_url, **kwargs):
            seen.update(kwargs)
            return "code"

        with patch.object(oauth_loopback, "capture_code", side_effect=capture), \
                patch(f"{_TIKTOK}.requests.post") as posted:
            posted.return_value = MagicMock(
                status_code=200,
                json=lambda: {"access_token": "at", "expires_in": 1})

            service.authenticate("default")

        self.assertEqual(seen["port"], 8562)

    def test_refresh_without_a_refresh_token_says_to_log_in_again(self):
        credential = OAuthCredential(
            account_id="default", access_token="at", refresh_token="",
            expires_at=datetime.now(timezone.utc))

        with self.assertRaises(OAuthError) as caught:
            self._service().refresh(credential)

        self.assertIn("다시 로그인", str(caught.exception))

    def test_an_error_in_the_user_info_body_is_a_failure(self):
        with patch(f"{_TIKTOK}.requests.get") as got:
            got.return_value = MagicMock(
                status_code=200,
                json=lambda: {"error": {"code": "access_token_invalid",
                                        "message": "토큰이 유효하지 않습니다"}})

            with self.assertRaises(OAuthError):
                self._service().fetch_channel_info(_credential())

    def test_the_display_name_becomes_the_account_name(self):
        with patch(f"{_TIKTOK}.requests.get") as got:
            got.return_value = MagicMock(
                status_code=200,
                json=lambda: {"data": {"user": {"open_id": "oid",
                                                "display_name": "웰빙플랜트"}},
                              "error": {"code": "ok"}})

            info = self._service().fetch_channel_info(_credential())

        self.assertEqual(info.channel_title, "웰빙플랜트")
        self.assertEqual(info.open_id, "oid")


# ══ 5. 토큰이 평문으로 남지 않는다 ═══════════════════════════════════

class TheTokensAreNotPlaintextTest(unittest.TestCase):

    def test_a_saved_refresh_token_is_not_readable_in_the_file(self):
        if not secret_box.available():
            self.skipTest("이 자리에서는 DPAPI를 쓸 수 없다")

        from app.providers.upload.file_token_store import FileTokenStore

        with tempfile.TemporaryDirectory() as tmp:
            where = os.path.join(tmp, "tokens.json")
            store = FileTokenStore(storage_path=where)

            store.save(OAuthCredential(
                account_id="default", access_token="ACCESS-NEEDLE",
                refresh_token="REFRESH-NEEDLE",
                expires_at=datetime.now(timezone.utc)))

            raw = open(where, encoding="utf-8").read()

        self.assertNotIn("REFRESH-NEEDLE", raw)
        self.assertNotIn("ACCESS-NEEDLE", raw)
        self.assertIn(secret_box.MARKER_DPAPI, raw)

    def test_what_was_saved_comes_back(self):
        from app.providers.upload.file_token_store import FileTokenStore

        with tempfile.TemporaryDirectory() as tmp:
            store = FileTokenStore(
                storage_path=os.path.join(tmp, "tokens.json"))

            store.save(OAuthCredential(
                account_id="default", access_token="a", refresh_token="r",
                expires_at=datetime.now(timezone.utc)))

            back = store.load("default")

        self.assertEqual(back.access_token, "a")
        self.assertEqual(back.refresh_token, "r")

    def test_a_token_file_written_before_this_change_still_opens(self):
        """
        이미 로그인해 둔 사람의 로그인이 판올림 한 번에 사라지면 안 된다.
        """

        from app.providers.upload.file_token_store import FileTokenStore

        with tempfile.TemporaryDirectory() as tmp:
            where = os.path.join(tmp, "tokens.json")

            with open(where, "w", encoding="utf-8") as f:
                json.dump({"default": {
                    "access_token": "old-a", "refresh_token": "old-r",
                    "expires_at": datetime.now(timezone.utc).isoformat(),
                }}, f)

            back = FileTokenStore(storage_path=where).load("default")

        self.assertEqual(back.refresh_token, "old-r")

    def test_an_unreadable_token_file_is_not_reported_as_logged_out(self):
        """
        풀 수 없는 파일을 빈 것으로 넘기면 화면은 "로그인 필요"라고
        말하고, 사람은 다시 로그인하면 되는 줄 안다 - 실제로는 다른
        Windows 계정에서 만든 파일이고 그 사실을 알아야 한다.
        """

        if not secret_box.available():
            self.skipTest("이 자리에서는 DPAPI를 쓸 수 없다")

        with self.assertRaises(OSError):
            secret_box.unwrap({
                secret_box.MARKER_KEY: secret_box.MARKER_DPAPI,
                secret_box.PAYLOAD_KEY: base64.b64encode(
                    b"not a real dpapi blob").decode("ascii"),
            })

    def test_the_screen_is_told_the_truth_about_at_rest(self):
        provider = social.TikTokAuthProvider(MagicMock())

        self.assertEqual(
            provider._at_rest(),
            "protected" if secret_box.available() else "plaintext")


# ══ 6. HTTP 경계 ═════════════════════════════════════════════════════

class TheHttpSurfaceTest(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.services import studio_jobs

        self.client = TestClient(app)
        studio_jobs.reset()
        self.addCleanup(studio_jobs.reset)

    def test_listing_accounts_works_without_any_credential(self):
        response = self.client.get("/studio/api/social/accounts")

        self.assertEqual(response.status_code, 200)

        body = response.json()
        platforms = [a["platform"] for a in body["accounts"]]

        self.assertEqual(sorted(platforms), sorted(social.PLATFORMS))
        self.assertIn(body["token_at_rest"], ("protected", "plaintext"))

    def test_no_account_claims_to_be_connected_without_a_token(self):
        body = self.client.get("/studio/api/social/accounts").json()

        for account in body["accounts"]:
            if account["state"] != "CONNECTED":
                with self.subTest(platform=account["platform"]):
                    self.assertFalse(account["connected"])

    def test_an_unknown_platform_is_refused(self):
        response = self.client.post("/studio/api/social/facebook/login")

        self.assertEqual(response.status_code, 400)
        self.assertIn("facebook", response.json()["detail"])

    def test_an_unknown_action_is_refused(self):
        response = self.client.post("/studio/api/social/youtube/hack")

        self.assertEqual(response.status_code, 400)

    def test_a_get_never_starts_a_login(self):
        """
        상태 조회로 브라우저가 열리면 안 된다 - 화면이 켜질 때마다
        불리는 자리다.
        """

        import webbrowser

        with patch.object(webbrowser, "open") as opened:
            self.client.get("/studio/api/social/accounts")

        opened.assert_not_called()

    def test_a_failed_action_still_hands_the_screen_something_to_draw(self):
        """
        "눌러도 아무 반응 없음"의 반대편이다. 실패해도 account 한 덩이가
        채워져 있어야 화면이 그릴 것이 있다.
        """

        import time as _time

        from app.services import studio_jobs

        with patch.object(
            social.SocialAuthManager, "provider",
            side_effect=RuntimeError("일부러 터뜨린다"),
        ):
            job_id = self.client.post(
                "/studio/api/social/tiktok/login").json()["job_id"]

            for _ in range(50):
                state = studio_jobs.status(job_id)

                if state["state"] != "running":
                    break

                _time.sleep(0.1)

        self.assertEqual(state["state"], "failed")
        self.assertIsNotNone(state["account"])
        self.assertFalse(state["account"]["connected"])
        self.assertIn("일부러 터뜨린다", state["account"]["message"])
        # traceback은 콘솔에 남는다 - 조용히 삼키지 않는다.
        self.assertTrue(any("Traceback" in line
                            for line in state["console"]))


# ══ 7. 화면 ══════════════════════════════════════════════════════════

class TheScreenTest(unittest.TestCase):

    def _page(self):
        from app.routers import studio as studio_router

        return studio_router.studio_page().body.decode("utf-8")

    def test_the_three_platforms_have_a_place(self):
        page = self._page()

        self.assertIn('id="socialBox"', page)

        for word in ("YouTube", "Instagram", "TikTok"):
            with self.subTest(word=word):
                self.assertIn(word, page)

    def test_the_handlers_are_declared(self):
        page = self._page()

        for name in ("loadSocial", "socialAction", "socialRow",
                     "showSocialError"):
            with self.subTest(name=name):
                self.assertIn(f"function {name}(", page)

    def test_setup_needed_is_drawn_differently_from_not_connected(self):
        page = self._page()

        self.assertIn("설정 필요", page)
        self.assertIn("연결 안 됨", page)

    def test_a_setup_needed_platform_offers_no_working_button(self):
        """눌러도 안 되는 단추를 내놓지 않는다."""

        page = self._page()
        at = page.index('const buttons = a.state === "NEEDS_SETUP"')

        self.assertIn("disabled", page[at:at + 220])

    def test_the_failure_path_writes_to_the_console(self):
        """예외를 조용히 삼키지 않는다 - 개발자 콘솔에도 남는다."""

        page = self._page()

        self.assertIn("console.error", page)

    def test_nothing_that_was_there_was_deleted(self):
        page = self._page()

        for word in ("YouTube 연결", "Google 로그인", 'id="oauthBox"',
                     "실제 업로드는 일어나지 않습니다"):
            with self.subTest(word=word):
                self.assertIn(word, page)


if __name__ == "__main__":
    unittest.main()
