"""
Sprint90 - Credential Health 상태/분류.

OneDrive 저장소의 desktop/application/oauth/credential_health.py를
그대로 옮긴 것이다. 원본에 Qt 의존이 없어 분류 규칙은 한 글자도
바꾸지 않았다 - 아래 문자열들은 실제 Google/Meta 응답에서 관측된
것이라 손대면 실측 근거가 사라진다.

원본 설명:
EPIC OAuth Manager + Publishing Operations - Credential Health 상태/분류.

app.providers.upload.oauth_service.OAuthError가 담고 있는 실제 Google
오류 메시지를 문자열로 분류한다(desktop.controllers.ai_chat_controller.
AIChatController._classify_error()와 동일한 관례 - 새 예외 타입을
만들지 않고, 이미 발생한 예외의 메시지를 그대로 읽는다).

"invalid_grant"/"Token has been expired or revoked"는 실제 Production
QA(이 Epic의 계기)에서 재현된 문자열 그대로다 - 지어낸 패턴이 아니라
GoogleOAuthService.refresh()가 실제로 던진 OAuthError.__str__()에
그대로 들어 있던 부분이다.

EPIC Instagram Connector (Production) - "OAuthException"/"Error
validating access token"은 Meta Graph API의 표준 오류 형식(공식 문서/
실사용 사례 기준, code 190)이다 - InstagramOAuthService.refresh()가
만료/폐기된 토큰에 대해 실제로 받는 응답 모양 그대로다.
"""

from dataclasses import dataclass

READY = "READY"
EXPIRED = "EXPIRED"
REAUTH_REQUIRED = "REAUTH_REQUIRED"
INVALID_SCOPE = "INVALID_SCOPE"
UNKNOWN = "UNKNOWN"

CREDENTIAL_HEALTH_OPTIONS = [READY, EXPIRED, REAUTH_REQUIRED, INVALID_SCOPE, UNKNOWN]

# 실제 Google/Meta OAuth2 오류 응답에 나타나는 문자열만 사용한다(추측 금지).
_REAUTH_REQUIRED_MARKERS = (
    "invalid_grant",
    "Token has been expired or revoked",
    "OAuthException",
    "Error validating access token",
)
_INVALID_SCOPE_MARKERS = (
    "insufficientPermissions",
    "insufficient authentication scopes",
    "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
)


@dataclass
class CredentialHealth:

    status: str
    message: str = ""
    checked_at: float = 0.0


def classify_error_message(message) -> str:
    if not message:
        return UNKNOWN
    if any(marker in message for marker in _REAUTH_REQUIRED_MARKERS):
        return REAUTH_REQUIRED
    if any(marker in message for marker in _INVALID_SCOPE_MARKERS):
        return INVALID_SCOPE
    return UNKNOWN
