"""
Sprint169 - Python 없이도 켤 수 있게 (Epic 58, Phase 1).

지금까지 이 프로그램을 켜려면 Python과 가상환경과 uvicorn 명령이
필요했다. 만드는 사람에게는 당연하지만, 쓰는 사람에게는 아니다.

이 파일이 하는 일은 넷뿐이다
----------------------------
    1. 사용자 자리를 만든다      output · .workflow · .dataset
    2. 서버를 띄운다            빈 포트를 찾아서
    3. 브라우저를 연다          그 주소로
    4. 끄는 길을 알려 준다      창을 닫거나 Ctrl+C

엔진을 부르지 않는다. 만드는 일은 화면에서 사람이 누를 때 시작된다.

포트를 고정하지 않는다
----------------------
8080이 이미 쓰이고 있으면 켜지지 않고, 그때 나는 오류는 사람이 읽을
수 있는 말이 아니다. 빈 포트를 물어보고 그 주소를 연다.

없는 것은 없다고 말한다
-----------------------
ffmpeg나 ffprobe가 없으면 영상이 만들어지지 않는다. 켤 때 한 번
알려 준다 - 몇 분 뒤에 알아볼 수 없는 오류로 아는 것보다 낫다.
"""

import os
import socket
import sys
import threading
import time
import webbrowser


HOST = "127.0.0.1"

# 켜지자마자 열지 않는다. 서버가 뜨기 전에 열면 빈 화면이 뜬다.
OPEN_AFTER_SECONDS = 1.5


def _free_port() -> int:
    """
    지금 비어 있는 포트. 운영체제가 골라 준다.

    고정하면 이미 쓰이고 있을 때 켜지지 않는다.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))

        return sock.getsockname()[1]


def _prepare_home() -> str:
    """사용자 것이 사는 자리를 만들어 둔다."""

    from app import runtime_paths

    runtime_paths.ensure(runtime_paths.home())
    runtime_paths.ensure(runtime_paths.output_root())
    runtime_paths.ensure(runtime_paths.workflow_root())
    runtime_paths.ensure(runtime_paths.dataset_root())

    return runtime_paths.home()


def _report_tools() -> list:
    """무엇이 없는지 한 번 말한다."""

    from app.services import media_tools

    missing = media_tools.missing()

    if missing:
        print()
        print("  [알림] 다음이 없어 영상을 만들 수 없습니다: "
              + ", ".join(missing))
        print("         프로그램 옆 ffmpeg 폴더에 넣거나 PATH에 두십시오.")

    return missing


def _open_browser(url: str) -> None:
    def later():
        time.sleep(OPEN_AFTER_SECONDS)

        try:
            webbrowser.open(url)
        except Exception:
            # 브라우저를 못 열어도 서버는 돈다. 주소는 이미 찍었다.
            pass

    threading.Thread(target=later, daemon=True).start()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    port = _free_port()
    url = f"http://{HOST}:{port}/studio"

    home = _prepare_home()

    print()
    print("  AI 영상제작소")
    print(f"  주소   {url}")
    print(f"  내 것  {home}")

    _report_tools()

    print()
    print("  끄려면 이 창을 닫거나 Ctrl+C 를 누르십시오.")
    print()

    # 바로 내보낸다. 묶인 프로그램의 출력을 파일이나 다른 창으로
    # 넘기면 버퍼에 갇혀 주소가 안 보인다 - 그러면 사람은 프로그램이
    # 멈춘 줄 안다.
    sys.stdout.flush()

    if "--no-browser" not in argv:
        _open_browser(url)

    import uvicorn

    from app.main import app

    try:
        uvicorn.run(app, host=HOST, port=port, log_level="warning")
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
