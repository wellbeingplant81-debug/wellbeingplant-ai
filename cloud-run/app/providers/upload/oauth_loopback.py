"""
Sprint217 - loopback 콜백을 한 곳에서 받는다 (Epic 61).

왜 이 파일이 생겼는가
---------------------
Instagram Provider가 제 안에 콜백 서버를 하나 들고 있었고, TikTok에도
같은 것이 필요했다. 두 벌이 되면 한쪽만 고치는 날이 온다 - 실제로
Instagram 쪽에는 `state` 검증이 아예 없었다(아래).

state를 검증하지 않으면 무엇이 뚫리는가
---------------------------------------
콜백 서버는 127.0.0.1의 정해진 포트에서 아무 요청이나 받는다. 그
사이에 브라우저의 다른 탭(또는 같은 PC의 다른 프로그램)이

    http://127.0.0.1:8551/callback?code=<공격자의_인가코드>

를 한 번 부르면, 우리는 그 코드를 우리 것으로 착각해 토큰으로
바꾸고 **공격자의 계정을 사용자 계정으로 저장한다**(OAuth 인가 코드
주입). 그래서 authorize에 실은 state를 콜백에서 되받아 같은지 본다.
다르면 코드를 버린다.

Instagram Provider는 state를 보내지도 받지도 않았다 - 이 파일을 쓰게
되면서 함께 막혔다.

무엇을 하지 않는가
------------------
토큰 교환을 하지 않는다. 각 플랫폼의 토큰 엔드포인트와 파라미터는
플랫폼마다 다르고, 그것은 각 Provider의 몫이다. 이 파일은 "브라우저를
열고, 인가 코드를 받아, state를 확인해 돌려준다"까지만 한다.
"""

import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from app.providers.upload.oauth_service import OAuthError

DEFAULT_TIMEOUT_SECONDS = 300.0

_DONE_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>로그인 완료</title></head>
<body style="font:16px system-ui;padding:40px;text-align:center">
<p>{message}</p>
<p style="color:#888;font-size:14px">이 창을 닫고 AI 영상제작소로 돌아가십시오.</p>
</body></html>"""


def new_state() -> str:
    """추측할 수 없는 state 한 개."""

    return secrets.token_urlsafe(32)


class _Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)

        self.server.received_code = (query.get("code") or [None])[0]
        self.server.received_state = (query.get("state") or [None])[0]
        self.server.received_error = (
            (query.get("error_description") or query.get("error") or [None])[0]
        )

        said = ("로그인이 완료되었습니다." if self.server.received_code
                else "로그인이 완료되지 않았습니다.")

        body = _DONE_HTML.format(message=said).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # 다른 Provider들과 같이 stdout을 스팸하지 않는다. 콘솔에는
        # 사람이 읽을 줄만 남긴다.
        pass


def open_browser(url: str) -> None:
    """
    시스템 기본 브라우저를 연다. 못 열면 그렇다고 말한다.

    webbrowser.open()은 실패를 예외로 던지지 않고 False를 돌려준다.
    그 False를 버리면, 브라우저가 안 열렸는데 프로그램은 콜백을
    기다리며 5분을 서 있는다 - 사람에게는 "눌러도 아무 반응 없음"이다.
    """

    try:
        opened = webbrowser.open(url)
    except Exception as exc:
        raise OAuthError(
            f"브라우저를 열지 못했습니다: {exc}. 아래 주소를 직접 "
            f"여십시오.\n{url}") from exc

    if not opened:
        raise OAuthError(
            "브라우저를 열지 못했습니다(시스템 기본 브라우저가 없거나 "
            f"열기를 거부했습니다). 아래 주소를 직접 여십시오.\n{url}")


def capture_code(
    auth_url: str, host: str, port: int, expected_state: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    platform: str = "",
) -> str:
    """
    브라우저를 열고 인가 코드를 받아 돌려준다.

    포트를 미리 잡고 나서 브라우저를 연다 - 순서를 뒤집으면 사람이
    로그인을 마친 뒤에야 "포트가 쓰이는 중"을 알게 되고, 그때는 이미
    인가 코드가 아무도 안 듣는 자리로 날아가 버린 뒤다.
    """

    label = f"{platform} " if platform else ""

    try:
        server = HTTPServer((host, port), _Handler)
    except OSError as exc:
        raise OAuthError(
            f"{label}로그인 응답을 받을 자리를 열지 못했습니다 "
            f"({host}:{port} - {exc}). 그 포트를 쓰고 있는 다른 "
            f"프로그램을 끄거나, 등록된 redirect URI의 포트를 "
            f"바꾸십시오.") from exc

    server.received_code = None
    server.received_state = None
    server.received_error = None
    # timeout을 안 주면 handle_request()가 무기한 블로킹해서 아래
    # deadline 확인이 두 번째 반복에서 평가될 기회조차 없다(Instagram
    # Provider가 실제로 겪어 고쳐 둔 것이다 - 그 교훈을 함께 옮긴다).
    server.timeout = min(1.0, timeout_seconds)

    try:
        open_browser(auth_url)

        deadline = time.time() + timeout_seconds

        while (server.received_code is None
               and server.received_error is None
               and time.time() < deadline):
            server.handle_request()
    finally:
        server.server_close()

    if server.received_error:
        raise OAuthError(
            f"{label}로그인이 거부되었습니다: {server.received_error}")

    if server.received_code is None:
        raise OAuthError(
            f"{label}로그인 응답을 받지 못했습니다(제한 시간 "
            f"{int(timeout_seconds)}초를 넘겼습니다). 브라우저에서 "
            f"로그인을 끝내지 않았거나 창을 닫으셨을 수 있습니다.")

    # 여기서 코드를 버릴 수 있어야 한다. 위의 검사를 다 지나온 코드도
    # 우리가 시작한 흐름의 것이 아닐 수 있다.
    if expected_state and server.received_state != expected_state:
        raise OAuthError(
            f"{label}로그인 응답의 state가 일치하지 않아 버렸습니다. "
            f"다른 창에서 시작된 응답이거나 가로채기일 수 있습니다. "
            f"다시 로그인하십시오.")

    return server.received_code
