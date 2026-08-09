"""
Sprint169 - Python 없이도 켤 수 있게 (Epic 58, Phase 1).
Sprint170 - 받은 사람이 그냥 켤 수 있게 (Epic 58, Phase 2).

이 파일이 하는 일은 다섯뿐이다
------------------------------
    1. 사용자 자리를 만든다      output · .workflow · .dataset · 설정
    2. 앉을 포트를 고른다        비어 있는 자리로
    3. 서버를 띄운다
    4. 브라우저를 연다           못 열면 그렇다고 말한다
    5. 죽으면 남긴다             창에는 한 줄, 파일에는 전부

엔진을 부르지 않는다. 만드는 일은 화면에서 사람이 누를 때 시작된다.

포트를 고정하지 않는다
----------------------
8080이 이미 쓰이고 있으면 켜지지 않고, 그때 나는 오류는 사람이 읽을
수 있는 말이 아니다. 비어 있는 자리를 골라 그 주소를 연다.

--port로 자리를 고를 수 있다. 그 자리가 차 있으면 멈추지 않고 다른
자리로 간다 - 멈춰 봐야 사람이 할 수 있는 일이 없다.

죽을 때 traceback을 창에 쏟지 않는다
------------------------------------
숨기려는 것이 아니다. 그 밑에 "무엇을 하십시오"라고 적어도 안 보이기
때문이다. traceback은 로그 파일에 있고, 창에는 그 파일이 어디 있는지가
남는다.
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
    """지금 비어 있는 포트. 운영체제가 골라 준다."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))

        return sock.getsockname()[1]


def _is_free(port: int) -> bool:
    """그 자리에 앉을 수 있는가."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
        except OSError:
            return False

    return True


def choose_port(preferred=None) -> int:
    """
    앉을 자리. 고른 자리가 차 있으면 비어 있는 자리로 간다.

    멈추지 않는 이유는, 멈춰 봐야 사람이 할 수 있는 일이 없기
    때문이다 - 무엇이 그 자리를 쓰고 있는지 우리는 모른다.
    """

    if preferred is None:
        return _free_port()

    if _is_free(preferred):
        return preferred

    other = _free_port()

    print(f"  [알림] {preferred}번 자리는 이미 쓰이고 있어 "
          f"{other}번으로 켭니다.")

    return other


def _asked_port(argv) -> int:
    """--port 로 고른 자리. 없거나 숫자가 아니면 None."""

    if "--port" not in argv:
        return None

    at = argv.index("--port") + 1

    if at >= len(argv):
        return None

    try:
        return int(argv[at])
    except ValueError:
        return None


def _prepare_home() -> str:
    """
    사용자 것이 사는 자리를 만들어 둔다.

    첫 실행이면 여기서 전부 생긴다. 두 번째부터는 이미 있으므로
    아무 일도 일어나지 않는다 - 있는 것을 건드리지 않는다.
    """

    from app import runtime_paths, settings

    runtime_paths.ensure(runtime_paths.home())
    runtime_paths.ensure(runtime_paths.output_root())
    runtime_paths.ensure(runtime_paths.workflow_root())
    runtime_paths.ensure(runtime_paths.dataset_root())

    # Sprint172 - 배경 음악을 넣을 자리. 넣으라고 말해 놓고 그 폴더가
    # 없으면, 사람은 만들어야 하는지 이름을 잘못 봤는지 알 수 없다.
    #
    # inbox까지 만든다 - 고르는 쪽이 보는 자리가 거기다. 위에만 만들면
    # 사람은 거기에 떨어뜨리고, 렌더는 마지막에 못 찾는다.
    runtime_paths.ensure(os.path.join(
        runtime_paths.home(), runtime_paths.MUSIC_DIRNAME,
        runtime_paths.MUSIC_INBOX))

    settings.ensure()

    return runtime_paths.home()


def _report_tools() -> list:
    """무엇이 없는지 한 번 말한다."""

    from app.services import media_tools

    missing = media_tools.missing()

    if missing:
        print()
        print("  [알림] 다음이 없어 영상을 만들 수 없습니다: "
              + ", ".join(missing))
        print("         프로그램 옆 "
              f"{media_tools.BESIDE_DIRNAME} 폴더에 넣으십시오.")

    return missing


def _report_music():
    """
    배경 음악이 있는가. 없으면 넣을 자리를 돌려준다.

    왜 켤 때 보는가
    ---------------
    렌더는 BGM을 반드시 하나 고른다. 없으면 몇 분을 쓴 뒤 마지막
    단계에서 죽고, 그때의 문장은 사람이 읽어도 무엇을 해야 하는지
    알 수 없다(Sprint171 실측: 묶은 프로그램은 이 이유로 단 한 번도
    렌더를 끝내지 못했다).

    Sprint172 - 넣을 자리를 알려 준다
    ---------------------------------
    예전에는 "묶는 사람이 넣어야 합니다"라고만 했다. 받은 사람이 할
    수 있는 일이 없는 안내였다. 이제 그 자리는 사용자 자리 아래이고,
    탐색기로 열어 mp3를 떨어뜨리면 된다.

    개발 중에는 저장소의 assets/music이 잡히므로 아무 말도 하지 않는다.
    """

    from app import runtime_paths

    where = runtime_paths.music_root()

    if runtime_paths._has_music(where):
        return None

    inbox = os.path.join(where, runtime_paths.MUSIC_INBOX)

    print()
    print("  [알림] 배경 음악이 없어 영상을 만들 수 없습니다.")
    print("         자료 준비와 검사까지는 그대로 됩니다.")
    print(f"         이 폴더에 mp3 를 넣으십시오: {inbox}")

    return where


def use_our_ffmpeg():
    """
    엔진이 들어오기 전에, 우리가 찾은 ffmpeg를 imageio에게 알려 준다.
    찾지 못하면 None.

    왜 필요한가
    -----------
    moviepy는 들이는 순간 imageio_ffmpeg.get_ffmpeg_exe()를 부르고,
    없으면 RuntimeError를 던진다 - 화면이 뜨기도 전이다.

    imageio는 제 것을 따로 들고 다니는데, 그러면 같은 ffmpeg가 두 벌
    실린다(Sprint171 실측: exe 안에 87MB, tools/에 또 87MB). 그래서
    번들에서 그것을 빼고, 대신 tools/의 것을 쓰라고 가리킨다.

    IMAGEIO_FFMPEG_EXE는 imageio가 스스로 정해 둔 문이다 - 우리가
    남의 내부를 뒤지는 것이 아니다.

    이미 사람이 정해 둔 값이 있으면 건드리지 않는다.
    """

    from app.services import media_tools

    found = media_tools.available()[media_tools.FFMPEG]

    if not found:
        return None

    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", found)

    return found


def _open_browser(url: str):
    """
    잠시 뒤에 브라우저를 연다. 띄운 스레드를 돌려준다.

    daemon이다 - 끄는 순간 이것 때문에 프로그램이 안 끝나면, 창은
    닫혔는데 포트는 물려 있는 상태가 된다.

    못 열어도 서버는 돈다. 다만 그렇다고 말한다 - 아무 일도 안
    일어나면 사람은 프로그램이 멈춘 줄 안다.
    """

    def later():
        time.sleep(OPEN_AFTER_SECONDS)

        try:
            webbrowser.open(url)
        except Exception:
            print()
            print("  [알림] 브라우저를 열지 못했습니다. "
                  f"주소를 직접 여십시오: {url}")

    thread = threading.Thread(target=later, daemon=True)
    thread.start()

    return thread


def _serve(argv) -> int:
    """켜는 일 전부. 죽으면 그대로 던진다 - 받는 자리는 main이다."""

    from app import app_info, settings

    port = choose_port(_asked_port(argv))
    url = f"http://{HOST}:{port}/studio"

    home = _prepare_home()

    print()
    print(f"  {app_info.title()}")
    print(f"  주소   {url}")
    print(f"  내 것  {home}")

    _report_tools()
    _report_music()

    print()
    print("  끄려면 이 창을 닫거나 Ctrl+C 를 누르십시오.")
    print()

    # 바로 내보낸다. 묶인 프로그램의 출력을 파일이나 다른 창으로
    # 넘기면 버퍼에 갇혀 주소가 안 보인다 - 그러면 사람은 프로그램이
    # 멈춘 줄 안다.
    sys.stdout.flush()

    wanted = ("--no-browser" not in argv
              and settings.load().get(settings.OPEN_BROWSER, True))

    # 엔진을 들이기 전에 봐야 한다. moviepy는 들이는 순간 ffmpeg를
    # 찾고, 없으면 라이브러리의 RuntimeError로 끝난다 - 그 문장에는
    # 무엇을 어디에 넣으라는 말이 없다.
    if use_our_ffmpeg() is None:
        from app.services import media_tools

        print("  ffmpeg 가 없어 시작할 수 없습니다.")
        print(f"  프로그램 옆 {media_tools.BESIDE_DIRNAME} 폴더에 "
              "ffmpeg.exe 를 넣고 다시 켜십시오.")
        print("  이 폴더는 통째로 두어야 합니다.")

        sys.stdout.flush()

        return 1

    if wanted:
        _open_browser(url)

    import uvicorn

    from app.main import app

    uvicorn.run(app, host=HOST, port=port, log_level="warning")

    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    try:
        return _serve(argv)
    except KeyboardInterrupt:
        # 사람이 끈 것이다. 오류가 아니다.
        return 0
    except BaseException as failed:
        from app import error_log

        written = error_log.write(failed)

        print()
        print("  프로그램을 켜지 못했습니다.")
        print(f"  {type(failed).__name__}: {failed}")

        if written:
            print(f"  자세한 것은 여기 적었습니다: {written}")
        else:
            print(f"  기록은 {error_log.DIRNAME} 폴더에 남기려 했으나 "
                  "그것마저 실패했습니다.")

        sys.stdout.flush()

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
