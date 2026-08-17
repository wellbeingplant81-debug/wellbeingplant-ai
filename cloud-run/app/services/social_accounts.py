"""
Sprint217 - SNS 계정 하나로 다룬다 (Epic 61).

    SocialAuthManager
          ├── youtube    GoogleOAuthService      + FileTokenStore
          ├── instagram  InstagramOAuthService   + InstagramTokenStore
          └── tiktok     TikTokOAuthService      + FileTokenStore

세 벌을 복사하지 않는다
-----------------------
로그인/로그아웃/상태확인의 뼈대는 이미 OAuthManager(Sprint90)에 있고
셋 다 그것을 그대로 쓴다. 이 파일이 새로 만드는 것은 그 위의 얇은
껍질 하나다 - "어느 플랫폼인가"와 "바깥 설정이 갖춰졌는가".

바깥 설정과 코드를 가른다
-------------------------
이것이 이 파일의 중심이다. 세 플랫폼의 막히는 자리가 서로 다르다.

    youtube    Google Cloud 설정 **완료**. client_secret.json이 자리에
               있으면 지금 로그인된다
    instagram  Meta 앱이 없다. INSTAGRAM_OAUTH_CLIENT_ID/SECRET 없음
    tiktok     TikTok 앱이 없다. TIKTOK_CLIENT_KEY/SECRET 없음

없는 것을 "연결 안 됨"으로 뭉개지 않는다. 연결 안 됨은 "누르면 된다"는
뜻이고, 설정 필요는 "눌러도 안 된다, 바깥에서 먼저 할 일이 있다"는
뜻이다 - 두 개를 같은 말로 적으면 사람은 단추를 누르며 시간을 버린다.

성공했다고 먼저 말하지 않는다
-----------------------------
connected는 저장된 자격증명이 실제로 있을 때만 True다. 토큰이 없으면
어떤 경로로도 True가 되지 않는다.
"""

import os

from app.services import credential_paths, oauth_health, secret_box

YOUTUBE = "youtube"
INSTAGRAM = "instagram"
TIKTOK = "tiktok"

PLATFORMS = (YOUTUBE, INSTAGRAM, TIKTOK)

LABELS = {
    YOUTUBE: "YouTube",
    INSTAGRAM: "Instagram",
    TIKTOK: "TikTok",
}

# 화면이 그리는 네 가지 상태.
CONNECTED = "CONNECTED"          # ● 연결됨
NEEDS_LOGIN = "NEEDS_LOGIN"      # ○ 연결 안 됨 / 다시 로그인 필요
NEEDS_SETUP = "NEEDS_SETUP"      # ○ 설정 필요 (바깥에서 할 일이 있다)
UNKNOWN = "UNKNOWN"              # ⚪ 알 수 없음


# 자주 나는 실패를 사람이 읽을 수 있는 말로 바꾼다.
#
# 왜 필요한가 - 실제로 화면에 이런 것이 떴다(바탕화면 exe에서 실측).
#
#   Google OAuth authentication failed for account default:
#   (mismatching_state) CSRF Warning! State not equal in request and response.
#
# 삼키지 않은 것은 옳다. 그런데 받은 사람이 저 글로 할 수 있는 일이
# 없다. 원문은 뒤에 그대로 붙여 둔다 - 우리가 알아볼 단서다.
_PLAIN = (
    ("mismatching_state",
     "로그인 응답이 우리가 시작한 것과 달라 취소했습니다. 다른 창에서 "
     "먼저 시작한 로그인이 남아 있을 수 있습니다. 다시 시도하십시오."),
    ("access_denied",
     "로그인 화면에서 동의하지 않으셨습니다. 다시 시도하십시오."),
    ("No such file or directory",
     "자격증명 파일을 찾지 못했습니다."),
    ("invalid_grant",
     "저장된 로그인이 더 이상 유효하지 않습니다(취소되었거나 "
     "만료되었습니다). 다시 로그인하십시오."),
    ("invalid_client",
     "자격증명이 이 앱과 맞지 않습니다. client_secret 파일을 "
     "확인하십시오."),
    ("insufficient",
     "권한이 부족합니다. 다시 로그인해 요청된 권한에 모두 동의해 "
     "주십시오."),
    ("Address already in use",
     "로그인 응답을 받을 포트가 이미 쓰이는 중입니다. 그 프로그램을 "
     "끄고 다시 시도하십시오."),
)

# 네트워크가 끊긴 것은 위와 달라서 따로 본다 - 사람이 할 일이 다르다.
_NETWORK = ("Failed to establish", "Connection aborted", "Max retries",
            "getaddrinfo", "Temporary failure in name resolution",
            "네트워크")


def plain_message(said: str) -> str:
    """
    실패 문장을 사람이 읽을 수 있게. 모르는 것은 그대로 둔다.

    지어내지 않는다 - 아는 모양만 바꾸고, 나머지는 원문이 낫다.
    """

    said = (said or "").strip()

    if not said:
        return ""

    for marker, plain in _PLAIN:
        if marker in said:
            return f"{plain} (원문: {said})"

    if any(marker in said for marker in _NETWORK):
        return ("인터넷에 연결하지 못했습니다. 연결을 확인하고 다시 "
                f"시도하십시오. (원문: {said})")

    return said


class SocialAccount:
    """한 플랫폼의 지금 상태. 화면이 이 모양만 안다."""

    def __init__(self, platform: str, state: str, message: str,
                 account_name: str = "", missing_setup=(),
                 setup_hint: str = "", token_at_rest: str = ""):
        self.platform = platform
        self.label = LABELS.get(platform, platform)
        self.state = state
        self.message = message
        self.account_name = account_name
        self.missing_setup = list(missing_setup)
        self.setup_hint = setup_hint
        self.token_at_rest = token_at_rest

    @property
    def connected(self) -> bool:
        return self.state == CONNECTED

    def as_dict(self) -> dict:
        return {
            "platform": self.platform,
            "label": self.label,
            "state": self.state,
            "connected": self.connected,
            "message": self.message,
            "account_name": self.account_name,
            "missing_setup": self.missing_setup,
            "setup_hint": self.setup_hint,
            "token_at_rest": self.token_at_rest,
        }


class SocialAuthProvider:
    """
    공통 인터페이스. 셋이 이것만 구현한다.

        login()             브라우저를 열고 끝까지 간다
        logout()            로컬 자격증명을 지운다
        is_authenticated()  저장된 것이 있는가 (네트워크 없음)
        get_account()       화면이 그릴 한 덩이
        refresh_token()     실제로 확인하고 필요하면 갱신한다
        missing_setup()     바깥에서 먼저 할 일들의 이름
    """

    platform = ""

    def __init__(self, manager):
        self.manager = manager

    # ── 바깥 설정 ─────────────────────────────────────────────────
    def missing_setup(self) -> list:
        return []

    def setup_hint(self) -> str:
        return ""

    # ── 상태 ──────────────────────────────────────────────────────
    def is_authenticated(self) -> bool:
        """저장된 자격증명이 있는가. 네트워크도 브라우저도 열지 않는다."""

        try:
            return self.manager.token_store.load(self.manager.account_id) \
                is not None
        except Exception:
            # 풀 수 없는 토큰 파일이 있는 경우다. "있다"고 말하면
            # 화면이 연결됨으로 그리므로 아니라고 답한다 - 왜인지는
            # get_account()가 말한다.
            return False

    def get_account(self) -> SocialAccount:
        missing = self.missing_setup()

        # 바깥 설정이 없어도 이미 받아 둔 토큰이 있으면 연결된 것이다 -
        # 설정이 사라졌다고 이미 연결된 계정을 부정하지 않는다.
        if missing and not self.is_authenticated():
            return SocialAccount(
                self.platform, NEEDS_SETUP,
                f"{' · '.join(missing)} 가 없어 로그인할 수 없습니다.",
                missing_setup=missing, setup_hint=self.setup_hint(),
                token_at_rest=self._at_rest(),
            )

        try:
            health = self.manager.check_health()
        except Exception as exc:
            return SocialAccount(
                self.platform, UNKNOWN, plain_message(str(exc)),
                missing_setup=missing, setup_hint=self.setup_hint(),
                token_at_rest=self._at_rest(),
            )

        state = self._state_for(health.status)

        return SocialAccount(
            self.platform, state, plain_message(health.message),
            # 연결됐을 때만 이름을 내놓는다. 끊긴 연결에 지난 이름을
            # 붙여 두면 화면은 "연결 안 됨"인데 이름은 남아 있어,
            # 어느 쪽이 사실인지 알 수 없게 된다.
            account_name=self._saved_name() if state == CONNECTED else "",
            missing_setup=missing, setup_hint=self.setup_hint(),
            token_at_rest=self._at_rest(),
        )

    # ── 동작 ──────────────────────────────────────────────────────
    def login(self) -> SocialAccount:
        health = self.manager.reauthenticate()
        account = self.get_account()

        # reauthenticate()가 실패를 health로 돌려주는 경로가 있다
        # (OAuthError를 잡아 UNKNOWN으로 바꾼다). 그 문장을 버리지
        # 않는다 - 사람이 읽어야 할 유일한 단서다.
        if health.status != oauth_health.READY:
            return SocialAccount(
                self.platform, self._state_for(health.status),
                plain_message(health.message),
                missing_setup=self.missing_setup(),
                setup_hint=self.setup_hint(), token_at_rest=self._at_rest(),
            )

        return account

    def logout(self) -> SocialAccount:
        self.manager.logout()
        self._forget_name()

        return self.get_account()

    def refresh_token(self) -> SocialAccount:
        """실제로 플랫폼에 물어본다. 만료면 갱신하고 계정 이름까지 받는다."""

        health = self.manager.verify_now()

        if health.status == oauth_health.READY:
            self._remember_name(health.message)

        return SocialAccount(
            self.platform, self._state_for(health.status),
            plain_message(health.message),
            account_name=self._saved_name(),
            missing_setup=self.missing_setup(),
            setup_hint=self.setup_hint(), token_at_rest=self._at_rest(),
        )

    # ── 잔가지 ────────────────────────────────────────────────────
    def _state_for(self, status: str) -> str:
        if status == oauth_health.READY:
            return CONNECTED
        if status in (oauth_health.REAUTH_REQUIRED, oauth_health.EXPIRED,
                      oauth_health.INVALID_SCOPE):
            return NEEDS_LOGIN
        return UNKNOWN

    def _at_rest(self) -> str:
        """토큰이 디스크에 어떻게 놓이는가. 화면이 그대로 보여 준다."""

        return "protected" if secret_box.available() else "plaintext"

    # 계정 이름은 verify_now()가 실제로 불러온 것만 기억한다.
    #
    # check_health()는 네트워크를 안 치므로 이름을 알 길이 없다. 그런데
    # 프로그램을 다시 켤 때마다 이름이 사라지면, 화면은 "연결됨"이라고만
    # 말하고 어느 계정에 연결됐는지는 [상태 확인]을 누를 때까지 알 수
    # 없다 - 여러 채널을 쓰는 사람에게는 그것이 곧 위험이다.
    #
    # 그래서 한 번 받아 온 이름은 적어 둔다. 이름은 비밀이 아니다 -
    # 공개된 채널 이름이고, 토큰과 달리 감쌀 것이 없다. 없는 이름을
    # 지어내지 않는다는 규칙은 그대로다 - 실제로 받아 온 것만 적힌다.
    def _names_path(self) -> str:
        return credential_paths.resolve(
            "SOCIAL_ACCOUNT_NAMES_PATH", "social_account_names.json")

    def _read_names(self) -> dict:
        import json

        try:
            with open(self._names_path(), encoding="utf-8") as f:
                found = json.load(f)
        except Exception:
            # 못 읽어도 화면은 그대로 돈다. 이름은 보조 정보다.
            return {}

        return found if isinstance(found, dict) else {}

    def _remember_name(self, message: str) -> None:
        said = (message or "").strip()

        # "OOO 채널에 연결됨." / "OOO 계정에 연결됨." 에서 이름만.
        for tail in (" 채널에 연결됨.", " 계정에 연결됨."):
            if not said.endswith(tail):
                continue

            name = said[:-len(tail)].strip()

            if not name:
                return

            import json

            names = self._read_names()
            names[self.platform] = name

            try:
                credential_paths.ensure_user_dir()

                where = self._names_path()

                os.makedirs(os.path.dirname(where) or ".", exist_ok=True)

                with open(where, "w", encoding="utf-8") as f:
                    json.dump(names, f, ensure_ascii=False, indent=2)
            except Exception:
                # 적지 못해도 이번 화면에는 이름이 보인다(아래 캐시).
                pass

            SocialAuthProvider._cache[self.platform] = name
            return

    def _forget_name(self) -> None:
        """로그아웃하면 이름도 잊는다 - 없는 연결의 이름을 남기지 않는다."""

        import json

        SocialAuthProvider._cache.pop(self.platform, None)

        names = self._read_names()

        if names.pop(self.platform, None) is None:
            return

        try:
            with open(self._names_path(), "w", encoding="utf-8") as f:
                json.dump(names, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    _cache = {}

    def _saved_name(self) -> str:
        if self.platform in SocialAuthProvider._cache:
            return SocialAuthProvider._cache[self.platform]

        return self._read_names().get(self.platform, "")


class YouTubeAuthProvider(SocialAuthProvider):

    platform = YOUTUBE

    def missing_setup(self) -> list:
        """
        Google Cloud 쪽 설정은 이미 끝나 있다(데스크톱 앱 클라이언트,
        redirect http://localhost). 남은 것은 그 파일이 이 PC의 제
        자리에 있는가뿐이다.
        """

        where = getattr(self.manager.oauth_service, "client_secret_path", "")

        if where and os.path.exists(where):
            return []

        return ["client_secret.json"]

    def setup_hint(self) -> str:
        where = getattr(self.manager.oauth_service, "client_secret_path", "")

        return (f"Google 데스크톱 앱 자격증명 파일을 여기에 두십시오: "
                f"{where}")


class InstagramAuthProvider(SocialAuthProvider):

    platform = INSTAGRAM

    def missing_setup(self) -> list:
        service = self.manager.oauth_service
        missing = []

        if not getattr(service, "client_id", ""):
            missing.append("INSTAGRAM_OAUTH_CLIENT_ID")
        if not getattr(service, "client_secret", ""):
            missing.append("INSTAGRAM_OAUTH_CLIENT_SECRET")

        return missing

    def setup_hint(self) -> str:
        where = getattr(self.manager.oauth_service, "redirect_uri", "")

        return ("Meta 개발자 콘솔에서 앱을 만들고 Instagram "
                "Business Login을 켠 뒤, App ID와 App Secret을 "
                f".env에 적고 Redirect URI로 {where} 를 등록해야 "
                "합니다. Meta는 프로덕션에서 HTTPS redirect를 "
                "요구하므로 로컬 HTTP만으로는 끝나지 않을 수 있습니다.")


class TikTokAuthProvider(SocialAuthProvider):

    platform = TIKTOK

    def missing_setup(self) -> list:
        service = self.manager.oauth_service

        if hasattr(service, "missing_setup"):
            return service.missing_setup()

        return []

    def setup_hint(self) -> str:
        where = getattr(self.manager.oauth_service, "redirect_uri", "")

        return ("TikTok for Developers에서 앱을 만들고 Login Kit을 켠 뒤, "
                "Client key와 Client secret을 .env에 적고 Redirect URI로 "
                f"{where} 를 등록해야 합니다.")


class SocialAuthManager:
    """세 Provider를 들고 있는 자리. 화면과 라우터는 이것만 본다."""

    def __init__(self, providers: dict):
        self.providers = providers

    def platforms(self) -> list:
        return [p for p in PLATFORMS if p in self.providers]

    def provider(self, platform: str) -> SocialAuthProvider:
        found = self.providers.get(platform)

        if found is None:
            raise KeyError(platform)

        return found

    def accounts(self) -> list:
        """
        전부의 지금 상태. 네트워크를 치지 않는다 - 화면을 열 때마다
        불려도 안전해야 하고, 무엇보다 브라우저가 저절로 열리면 안 된다.
        """

        return [self.provider(p).get_account() for p in self.platforms()]


def build_default_social_auth_manager() -> SocialAuthManager:
    from app.providers.upload.file_token_store import FileTokenStore
    from app.providers.upload.tiktok_oauth_service import (
        build_default_tiktok_oauth_service,
    )
    from app.services import instagram_oauth_manager, oauth_manager

    tiktok_tokens = credential_paths.resolve(
        "TIKTOK_OAUTH_TOKEN_STORE_PATH", "tiktok_oauth_tokens.json")

    tiktok = oauth_manager.OAuthManager(
        oauth_service=build_default_tiktok_oauth_service(),
        token_store=FileTokenStore(storage_path=tiktok_tokens),
        account_id=os.environ.get("TIKTOK_OAUTH_ACCOUNT_ID", "default"),
    )

    return SocialAuthManager({
        YOUTUBE: YouTubeAuthProvider(
            oauth_manager.build_default_oauth_manager()),
        INSTAGRAM: InstagramAuthProvider(
            instagram_oauth_manager.build_default_instagram_oauth_manager()),
        TIKTOK: TikTokAuthProvider(tiktok),
    })
