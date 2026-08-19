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
#
# Sprint219 - 이 값만으로는 부족하다는 것이 드러났다. 아래
# _wait_until_serving를 함께 읽을 것. 이 값은 포트를 모르는 자리에서만
# 쓰인다.
OPEN_AFTER_SECONDS = 1.5

# Sprint219 - 서버가 실제로 받을 때까지 기다리는 최대 시간.
#
# 왜 필요한가 - 아래 _wait_until_serving의 설명을 볼 것. 넉넉히 둔다.
# 이 시간을 넘겨도 안 뜨면 브라우저를 열지 않는다 - 죽은 주소를 여는
# 것은 아무것도 안 여는 것보다 나쁘다("안 된다"고 잘못 가르친다).
WAIT_FOR_SERVER_SECONDS = 90.0

# Sprint219 - 켜지는 동안 무엇을 지났는지 적어 두는 자리.
STARTUP_LOG = "startup.log"

# 그 파일이 무한정 자라지 않게 한다. 한 번 켤 때 열 줄쯤이다.
STARTUP_LOG_MAX_LINES = 400

# 자취가 사는 폴더. logs/ 가 **아니다.**
#
# logs/ 는 "무언가 잘못됐다"는 뜻으로 지켜 온 자리다 - 잘 켜졌을 때는
# 만들지도 않는다("빈 logs 폴더는 무슨 일이 있었나 하게 만든다",
# test_rc_final_check가 그것을 붙잡고 있다). 켤 때마다 남기는 자취를
# 거기 두면 그 뜻이 사라진다.
#
# .dataset 은 쌓인 관측이 사는 자리이고 어차피 켤 때마다 생긴다.
# 자취는 그쪽이 맞다. 대신 죽을 때는 이 자취를 오류 기록에 함께
# 붙인다 - README가 "logs 폴더의 파일을 보내 주십시오"라고 말하므로,
# 보내 준 그 파일 하나에 다 들어 있어야 한다.
TRAIL_DIRNAME = ".dataset"

# Sprint226 - 그만 기다려도 된다는 신호.
#
# 브라우저를 여는 일은 서버가 실제로 받을 때까지 기다린다(최대 90초).
# 그런데 그 사이에 서버 쪽이 먼저 끝나 버리면, 기다림은 뜻을 잃는다 -
# 창이 닫혔는데 브라우저를 열려고 90초를 더 기다리는 셈이다.
#
# 실측으로 걸렸다. 회귀가 끝난 뒤에도 이 스레드 하나가 남아 있었다
# (Thread-N (later), daemon). 데몬이라 프로그램을 붙잡지는 않지만,
# "끝났는데 아직 무언가 돌고 있다"는 상태 자체가 결함이다.
_STOP_WAITING = threading.Event()


def _trail_dir() -> str:
    """
    자취를 남길 자리. 못 구하면 빈 문자열.

    runtime_paths를 먼저 쓰되 실패하면 손으로 구한다.

    왜 이 중복을 허용하는가
    -----------------------
    이 함수가 존재하는 이유가 "app 패키지가 안 올라와도 이유를
    남긴다"이다. 그런데 app.runtime_paths를 들이는 데 실패하면 바로
    그 순간 아무것도 못 남긴다 - 가장 알고 싶은 실패에서 입을 다무는
    셈이다. 그래서 그때만 쓰는 최소한의 대체 경로를 둔다.
    """

    try:
        from app import runtime_paths

        return os.path.join(runtime_paths.home(), TRAIL_DIRNAME)
    except Exception:
        pass

    given = os.environ.get("AI_STUDIO_HOME")

    if given:
        return os.path.join(given, TRAIL_DIRNAME)

    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")

        return os.path.join(base, "AI영상제작소", TRAIL_DIRNAME)

    return ""


def trail_path() -> str:
    """자취 파일의 자리. 못 구하면 빈 문자열."""

    where = _trail_dir()

    return os.path.join(where, STARTUP_LOG) if where else ""


def note(step: str, where: str = None) -> None:
    """
    켜는 도중 어디까지 왔는지 한 줄 적는다. 절대 던지지 않는다.

    왜 이것이 이번 Sprint의 중심인가
    --------------------------------
    사용자가 "두 번 눌러도 아무 반응이 없다"고 했을 때, 이 프로그램이
    남긴 것은 **아무것도 없었다** - 스물네 번 켜는 동안 logs 폴더는
    만들어진 적조차 없다(실측). 창은 순식간에 닫히고, 오류 기록은
    예외가 났을 때만 쓰이는데 조용히 return으로 끝나는 길이 여럿이다.

    그래서 무엇이 잘못됐는지 우리도 사용자도 알 수 없었다. 다음에는
    이 파일이 답한다.

    기록 자체가 프로그램을 멈추게 하면 안 된다 - 그래서 무슨 일이
    있어도 조용히 넘긴다. 관찰이 제품을 멈추게 하면 관찰을 켠 것이
    잘못이 된다(beta_telemetry가 이미 그렇게 한다).

    Sprint224 - where 를 주면 그 자리에 적는다
    ------------------------------------------
    나중에 적는 자리가 하나 있다. 브라우저를 기다리는 스레드는 최대
    WAIT_FOR_SERVER_SECONDS(90초)를 더 기다린 뒤에야 적는데, 그때
    자리를 다시 구하면 **그 사이에 바뀐 자리**에 적힌다.

    자취는 이 프로그램이 켜진 그 집에 남아야 한다. 그래서 늦게 적는
    쪽은 태어날 때 받은 자리를 들고 간다(_open_browser 참고).
    """

    where = where or _trail_dir()

    if not where:
        return

    try:
        os.makedirs(where, exist_ok=True)

        path = os.path.join(where, STARTUP_LOG)

        # 너무 길어지면 앞을 버린다. 최근 것이 알고 싶은 것이다.
        lines = []

        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()[-STARTUP_LOG_MAX_LINES:]
            except Exception:
                lines = []

        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{stamp}  {step}\n")

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass

# Sprint174 - 피드백 폴더에 남겨 두는 안내.
#
# 빈 폴더는 무엇을 적으라는 말이 아니다. 무엇이 있어야 우리가 고칠
# 수 있는지는 우리가 안다 - 사람이 짐작하게 두지 않는다.
FEEDBACK_NOTE = "무엇을 적으면 되나요.txt"


def _feedback_note(where: str) -> str:
    """
    적는 법을 적어 둔다. 이미 있으면 손대지 않는다.

    사람이 이 파일에 그냥 이어 적을 수도 있다. 켤 때마다 덮으면 그
    사람의 글이 사라진다 - 설정에서 정한 규칙과 같다.
    """

    from app import app_info, error_log

    path = os.path.join(where, FEEDBACK_NOTE)

    if os.path.exists(path):
        return path

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""겪으신 일을 이 폴더에 적어 주십시오.

파일 이름은 아무렇게나 지으셔도 됩니다.
예) 2026-08-09 이미지가 안 걸림.txt

무엇을 적으면 도움이 되나요
---------------------------
    1. 무엇을 하려던 참이었는지
    2. 무엇을 눌렀는지
    3. 무엇이 나왔는지 (화면에 뜬 글을 그대로)

여기에 두 가지를 함께 넣어 주시면 훨씬 빨리 찾습니다.

    화면 오른쪽 위 [정보 복사] 를 누르고 붙여넣기
    프로그램이 아예 안 켜졌다면 {error_log.DIRNAME} 폴더의 파일

보내실 곳
---------
{app_info.CONTACT}

이 폴더는 프로그램이 지우지 않습니다. 새 판을 덮어씌워도 남습니다.
""")

    return path


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

    # Sprint174 - 겪은 일을 적어 둘 자리와, 무엇을 적으면 되는지.
    _feedback_note(runtime_paths.ensure(runtime_paths.feedback_root()))

    settings.ensure()

    # Sprint175 - 켰다고 적는다. 몇 번째인지와 언제인지뿐이다 -
    # 누가·무엇을은 적지 않는다.
    #
    # 못 적어도 켜진다. 관찰이 제품을 멈추게 하면 관찰을 켠 것이
    # 잘못이 된다.
    try:
        from app.services import beta_telemetry

        beta_telemetry.launched()
    except Exception:
        pass

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


def _serving(port: int) -> bool:
    """그 자리가 지금 연결을 받는가."""

    try:
        with socket.create_connection((HOST, port), 0.25):
            return True
    except OSError:
        return False


def _wait_until_serving(port: int,
                        timeout: float = None,
                        stop=None) -> bool:
    """
    서버가 실제로 받기 시작할 때까지 기다린다. 받으면 True.

    Sprint219 - 이 함수가 고치는 실제 결함
    --------------------------------------
    예전에는 1.5초를 세고 브라우저를 열었다. 그런데 그 1.5초 뒤에
    일어나는 일이 이 프로그램에서 가장 무거운 것이다.

        import uvicorn
        from app.main import app     <- moviepy · google · fastapi …

    묶은 프로그램을 찬 상태에서 켜면 이 두 줄이 1.5초를 훌쩍 넘긴다.
    그 사이에 브라우저는 아직 아무도 듣지 않는 주소를 열고, 사람은
    "연결할 수 없음"을 본다. 서버가 몇 초 뒤에 떠도 그 탭은 그대로다 -
    새로 고치라고 알려 주는 것도 없다.

    받는 사람에게 이것은 "눌렀는데 안 켜진다"와 구별되지 않는다.

    1.5초를 늘리는 것으로는 못 고친다 - 빠른 PC에서는 그만큼 늦어지고
    느린 PC에서는 여전히 모자란다. 시간을 재지 말고 **실제로 받는지**를
    본다.
    """

    deadline = time.time() + (
        WAIT_FOR_SERVER_SECONDS if timeout is None else timeout)

    while time.time() < deadline:
        # Sprint226 - 서버 쪽이 먼저 끝났으면 더 기다릴 것이 없다.
        if stop is not None and stop.is_set():
            return _serving(port)

        if _serving(port):
            return True

        time.sleep(0.2)

    return _serving(port)


def _open_browser(url: str, ready_port: int = None):
    """
    브라우저를 연다. 띄운 스레드를 돌려준다.

    ready_port를 주면 그 자리가 실제로 받을 때까지 기다렸다가 연다.
    주지 않으면 예전처럼 잠깐 세고 연다 - 포트를 모르면 기다릴 방법이
    없다.

    daemon이다 - 끄는 순간 이것 때문에 프로그램이 안 끝나면, 창은
    닫혔는데 포트는 물려 있는 상태가 된다.

    못 열어도 서버는 돈다. 다만 그렇다고 말한다 - 아무 일도 안
    일어나면 사람은 프로그램이 멈춘 줄 안다.

    Sprint224 - 자취를 남길 자리를 태어날 때 정한다
    ----------------------------------------------
    이 스레드는 서버를 최대 90초 기다린 뒤에야 적는다. 그 안에서
    자리를 다시 구하면 **그 사이에 바뀐 자리**에 적힌다.

    실측으로 걸렸다. 자리를 A로 두고 스레드를 띄운 뒤 A를 B로 바꾸자
    자취가 B에 남았다 - 켠 집이 아니라 지금 집에 적힌 것이다. 회귀에서
    이것이 다른 시험의 임시 집에 .dataset을 만들어 그 시험을 깨뜨렸다
    (test_script_input_contract, "읽어 보는 것만으로 아무것도 생기면
    안 된다").

    자취는 이 프로그램이 켜진 그 집에 남아야 한다.
    """

    # 지금 정한다. 90초 뒤가 아니라.
    trail = _trail_dir()

    # Sprint226 - 이 기다림은 지금 시작한다.
    #
    # "그만 기다려도 된다"는 신호는 **이 켜기의 서버가 끝났다**는 뜻이다.
    # 지난번 켜기가 남긴 신호가 그대로 있으면 새 기다림이 시작하자마자
    # 포기한다 - 실측으로 걸렸다(한 프로세스에서 두 번 켜는 시험).
    _STOP_WAITING.clear()

    def later():
        if ready_port is None:
            time.sleep(OPEN_AFTER_SECONDS)
        elif not _wait_until_serving(ready_port, stop=_STOP_WAITING):
            # 죽은 주소를 열지 않는다. 여는 것이 "안 된다"고 잘못
            # 가르치는 것보다, 아직 준비 중이라고 말하는 편이 낫다.
            note("browser: server never came up, not opening", where=trail)

            print()
            print("  [알림] 서버가 아직 응답하지 않아 브라우저를 열지 "
                  "않았습니다.")
            print(f"         준비되면 이 주소를 여십시오: {url}")

            sys.stdout.flush()

            return

        note("browser: opening", where=trail)

        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False

        if opened is False:
            note("browser: could not open", where=trail)

            print()
            print("  [알림] 브라우저를 열지 못했습니다. "
                  f"주소를 직접 여십시오: {url}")

            sys.stdout.flush()

    thread = threading.Thread(target=later, daemon=True)
    thread.start()

    return thread


# ── 끄면 정말 끝나게 ──────────────────────────────────────────────
#
# 실측으로 드러난 것(Sprint230 뒷마무리)
# -------------------------------------
# 묶은 프로그램은 프로세스가 둘이다. PyInstaller의 부트로더가 제 옆에
# 자식을 하나 띄우고, **서버는 그 자식**이다.
#
#     부트로더 44348  →  자식 29428 (여기서 uvicorn이 돈다)
#
# 부트로더를 강제로 끝내면 자식이 남는다. 실측: 부모를 죽인 뒤 3초가
# 지나도 자식이 살아 있고 포트도 계속 잡고 있었다. 그렇게 쌓인 것이
# 여섯 개였고, 그중 하나가 dist의 exe를 물고 있어서 다음 묶기가
# WinError 5로 죽었다 - "액세스가 거부되었습니다".
#
# 사람이 창을 닫거나 Ctrl+C를 누르면 콘솔이 둘 다에게 알려 주므로
# 이 길로 오지 않는다. 여기서 막는 것은 **강제 종료**다 - 작업
# 관리자, 그리고 시험/묶기 스크립트의 timeout.
#
# 두 가지를 건다
# --------------
#     부모 지킴이   부모가 사라지면 우리도 나간다
#     Job Object   우리가 죽으면 자손(ffmpeg)도 함께 정리된다
#
# 둘이 서로를 대신하지 못한다. Job은 "내가 죽을 때 자손"을 맡고,
# 지킴이는 "부모가 죽을 때 나"를 맡는다. Job을 만드는 주체가 곧 죽는
# 대상이므로, Job만으로는 이 누수가 고쳐지지 않는다.

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9

# 만든 Job을 붙잡아 둔다. 놓으면 핸들이 닫히고 그 순간 규칙이 발동해
# 우리 자신까지 죽는다.
_job = None

# 부모가 사라진 뒤 곱게 끝나기를 기다리는 시간. 이 시간을 넘기면
# 그대로 나간다 - 남아 있는 것이 더 나쁘다.
GRACE_AFTER_PARENT_GONE = 8.0


def own_children() -> bool:
    """
    우리가 죽으면 자손도 함께 죽게 만든다. 성공하면 True.

    렌더는 moviepy가 ffmpeg를 자식으로 띄워서 한다. 그 자식을 붙잡아
    두는 코드가 이 저장소에 없다 - Popen 핸들을 moviepy가 제 안에
    들고 있다. 그래서 운영체제에 관계를 등록한다. 우리가 어떻게 죽든
    같은 일이 일어난다.

    실패해도 켜진다. 이미 다른 Job에 들어 있는 자리가 있을 수 있고,
    그때 못 켜는 것은 과한 대가다.
    """

    global _job

    if _job is not None:
        return True

    if not sys.platform.startswith("win"):
        return False

    import ctypes
    from ctypes import wintypes

    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.POINTER(wintypes.ULONG)),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount",
            "OtherOperationCount", "ReadTransferCount",
            "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimit),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.windll.kernel32

    # restype을 주지 않으면 64비트 핸들이 int로 잘려 뒤의 호출이 전부
    # 실패한다. 실패 이유가 "핸들이 이상하다"뿐이어서 찾기 어렵다.
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,
                                                  wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    try:
        handle = kernel32.CreateJobObjectW(None, None)

        if not handle:
            return False

        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = \
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        if not kernel32.SetInformationJobObject(
                handle, JobObjectExtendedLimitInformation,
                ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(handle)

            return False

        if not kernel32.AssignProcessToJobObject(
                handle, kernel32.GetCurrentProcess()):
            kernel32.CloseHandle(handle)

            return False
    except Exception:
        return False

    _job = handle

    return True


def parent_pid() -> int:
    """
    나를 띄운 프로세스의 번호. 못 구하면 0.

    psutil을 쓰지 않는다 - 이 저장소의 의존이 아니고, 이것 하나 때문에
    묶음이 커질 이유가 없다.
    """

    if not sys.platform.startswith("win"):
        return 0

    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002

    class _Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

    try:
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    except Exception:
        return 0

    if not snap or snap == wintypes.HANDLE(-1).value:
        return 0

    mine = os.getpid()
    entry = _Entry()
    entry.dwSize = ctypes.sizeof(_Entry)

    try:
        if not kernel32.Process32First(snap, ctypes.byref(entry)):
            return 0

        while True:
            if entry.th32ProcessID == mine:
                return int(entry.th32ParentProcessID)

            if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                return 0
    except Exception:
        return 0
    finally:
        kernel32.CloseHandle(snap)


def _leave_when_parent_goes(pid: int) -> None:
    """
    부모가 사라지면 우리도 나간다. 절대 던지지 않는다.

    곱게 끝내는 것을 먼저 시도한다 - SIGINT를 우리 자신에게 보낸다.
    uvicorn이 그것을 받아 정리하고 uvicorn.run이 돌아오면, 평소 끄는
    길을 그대로 지난다(_STOP_WAITING도 그 자리에서 놓인다).

    uvicorn.run을 uvicorn.Server로 바꾸지 않는다 - 시험 여섯 자리가
    uvicorn.run을 patch해서 실제 서버가 뜨지 않게 막고 있다. 그 약속을
    깨면 회귀가 서버를 켜기 시작한다.

    그래도 안 끝나면 그대로 나간다. 남아서 포트와 exe를 물고 있는 것이
    더 나쁘다 - 그 때문에 다음 묶기가 죽었다.
    """

    import ctypes
    from ctypes import wintypes

    SYNCHRONIZE = 0x00100000

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE

    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)

    if not handle:
        # 부모가 이미 없거나 볼 수 없다. 지켜볼 것이 없다.
        note(f"parent watch: cannot open parent {pid}")

        return

    try:
        kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
    finally:
        kernel32.CloseHandle(handle)

    note(f"parent watch: parent {pid} is gone, leaving")

    # 기다리던 쪽에게 먼저 알린다.
    _STOP_WAITING.set()

    try:
        import signal

        signal.raise_signal(signal.SIGINT)
    except Exception:
        pass

    time.sleep(GRACE_AFTER_PARENT_GONE)

    note("parent watch: still here after grace, exiting hard")

    os._exit(0)


def watch_parent() -> int:
    """
    부모 지킴이를 띄운다. 지켜보는 부모의 번호, 안 띄웠으면 0.

    **묶였을 때만 띄운다.** 개발 중에는 부모가 셸이나 pytest이고, 그것이
    끝날 때 우리가 os._exit을 부르면 시험 자체를 끝내 버린다. 실제로
    위험한 쪽이라 여기서 확실히 가른다.
    """

    if not getattr(sys, "frozen", False):
        return 0

    pid = parent_pid()

    if not pid:
        note("parent watch: no parent found")

        return 0

    thread = threading.Thread(target=_leave_when_parent_goes, args=(pid,),
                              daemon=True, name="parent-watch")
    thread.start()

    note(f"parent watch: watching {pid}")

    return pid


def _serve(argv) -> int:
    """켜는 일 전부. 죽으면 그대로 던진다 - 받는 자리는 main이다."""

    # Sprint226 - 이번 켜기는 이제부터다. 지난번의 "그만"이 남아
    # 있으면 브라우저가 열리기도 전에 포기한다.
    _STOP_WAITING.clear()

    # 가장 먼저 건다. 뒤에서 태어나는 것(ffmpeg)이 이미 Job 안에
    # 있어야 하고, 부모가 그 사이에 사라져도 알아야 한다.
    if not own_children():
        note("serve: job object not set")

    watch_parent()

    note("serve: importing app_info/settings")

    from app import app_info, settings

    port = choose_port(_asked_port(argv))
    url = f"http://{HOST}:{port}/studio"

    note(f"serve: port {port}")

    home = _prepare_home()

    note("serve: home ready")

    print()
    print(f"  {app_info.title()}")
    print(f"  주소   {url}")
    print(f"  내 것  {home}")

    _report_tools()
    _report_music()

    # Sprint174 - 막혔을 때 갈 곳. 곤란해진 다음에 찾아 헤매게 하면
    # 아무도 안 쓴다.
    from app import runtime_paths

    print()
    print(f"  겪은 일   {runtime_paths.feedback_root()} 에 적어 주십시오")
    print(f"  문의      {app_info.CONTACT}")

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

        note("serve: STOP - ffmpeg not found")

        print("  ffmpeg 가 없어 시작할 수 없습니다.")
        print(f"  프로그램 옆 {media_tools.BESIDE_DIRNAME} 폴더에 "
              "ffmpeg.exe 를 넣고 다시 켜십시오.")
        print("  이 폴더는 통째로 두어야 합니다.")

        sys.stdout.flush()

        return 1

    note("serve: ffmpeg ok")

    if wanted:
        # Sprint219 - 포트를 함께 준다. 이것이 있어야 브라우저가
        # 서버보다 먼저 열리지 않는다.
        _open_browser(url, ready_port=port)

    note("serve: importing uvicorn and app (the heavy part)")

    import uvicorn

    from app.main import app

    note("serve: engine imported, handing over to uvicorn")

    try:
        uvicorn.run(app, host=HOST, port=port, log_level="warning")
    finally:
        # Sprint226 - 서버가 끝났다. 브라우저를 기다리던 쪽에게
        # 그만해도 된다고 말한다 - 죽어도 알려 주고 나간다.
        _STOP_WAITING.set()

    note("serve: uvicorn returned (window closed or Ctrl+C)")

    return 0


def _attach_trail(error_log_path: str) -> None:
    """
    켤 때 남긴 자취를 오류 기록 끝에 붙인다. 절대 던지지 않는다.

    붙이는 이유는 하나다 - 사람이 보내 주는 것이 그 파일 한 개다.
    """

    if not error_log_path:
        return

    path = trail_path()

    if not path or not os.path.exists(path):
        return

    try:
        with open(path, encoding="utf-8") as f:
            trail = f.readlines()[-60:]

        with open(error_log_path, "a", encoding="utf-8") as f:
            f.write("\n\n--- 켤 때 지나온 자취 ---\n")
            f.writelines(trail)
    except Exception:
        pass


def _hold_console(argv) -> None:
    """
    켜지 못했을 때 창을 붙잡아 둔다.

    Sprint219 - 왜 필요한가
    -----------------------
    아이콘을 두 번 눌러 켜면 Windows가 새 콘솔 창을 만든다. 그 창은
    프로그램이 끝나는 순간 사라진다 - 무엇이 잘못됐다고 적어 놓아도
    사람이 읽을 시간이 없다. 화면이 번쩍하고 마는 것이 곧 "아무 반응
    없음"이다.

    자동으로 돌리는 자리에서는 붙잡지 않는다 - 붙잡으면 그 자리가
    영원히 멈춘다. 사람이 보고 있는 창인지는 stdin이 말해 준다.
    """

    if "--no-hold" in argv:
        return

    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
    except Exception:
        return

    try:
        print()
        print("  이 창을 닫으면 끝납니다. Enter 를 누르셔도 됩니다.")
        sys.stdout.flush()
        sys.stdin.readline()
    except Exception:
        pass


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    note("=" * 8 + " launch " + "=" * 8)
    note(f"frozen={bool(getattr(sys, 'frozen', False))} cwd={os.getcwd()}")

    try:
        code = _serve(argv)
    except KeyboardInterrupt:
        # 사람이 끈 것이다. 오류가 아니다.
        note("exit: Ctrl+C")

        return 0
    except BaseException as failed:
        note(f"exit: FAILED {type(failed).__name__}: {failed}")

        from app import error_log

        written = error_log.write(failed)

        # 자취를 그 파일에 함께 붙인다. README는 "logs 폴더의 파일을
        # 보내 주십시오"라고 말한다 - 보내 준 그 하나에 어디까지
        # 갔었는지도 들어 있어야 우리가 읽을 수 있다.
        _attach_trail(written)

        print()
        print("  프로그램을 켜지 못했습니다.")
        print(f"  {type(failed).__name__}: {failed}")

        if written:
            print(f"  자세한 것은 여기 적었습니다: {written}")
        else:
            print(f"  기록은 {error_log.DIRNAME} 폴더에 남기려 했으나 "
                  "그것마저 실패했습니다.")

        sys.stdout.flush()

        _hold_console(argv)

        return 1

    note(f"exit: code {code}")

    # 조용히 1로 끝나는 길이 여럿이다(ffmpeg 없음 등). 그때도 창이
    # 사라지면 적어 놓은 이유를 아무도 못 읽는다.
    if code != 0:
        _hold_console(argv)

    return code


if __name__ == "__main__":
    raise SystemExit(main())
