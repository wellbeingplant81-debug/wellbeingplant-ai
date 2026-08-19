"""
Sprint220 - Desktop Host 프로토타입 (Phase 1).

    python host_desktop.py                  창을 띄운다
    python host_desktop.py --check          창 없이 서버 길만 확인한다
    python host_desktop.py --confirm-close  닫을 때 언제나 한 번 더 묻는다

무엇을 증명하려고 만든 파일인가
-------------------------------
하나뿐이다 - **기존 것을 한 줄도 고치지 않고 WebView2 안에서 그대로
쓸 수 있는가.**

그래서 이 파일은 새로 만드는 것이 거의 없다. 서버는 app.main의 것을
그대로 쓰고, 화면은 app/static/studio.html을 그대로 연다. 포트를
고르는 일과 서버가 뜰 때까지 기다리는 일은 launcher.py의 것을
**가져다 쓴다** - 베끼면 둘 중 하나만 고치는 날이 오고, 그날 두
진입점은 서로 다른 프로그램이 된다.

launcher.py를 고치지 않는다
---------------------------
이 파일은 그 옆에 서는 **두 번째 진입점**이다. 기존 진입점은 그대로
살아 있고, 지금 쓰고 계신 exe도 그대로 켜진다. 이 파일을 지우면
아무 일도 일어나지 않는다 - 그것이 이번 Sprint의 안전장치다.

무엇을 하지 않는가
------------------
영상 제작 로직을 넣지 않는다. OAuth를 건드리지 않는다 - 로그인은
지금처럼 시스템 기본 브라우저로 나간다(Google은 임베디드 웹뷰에서의
로그인을 거부한다). AI Bridge를 부르지 않는다.

창을 먼저 띄우고 서버를 뒤에 붙이는 이유
----------------------------------------
Sprint219가 붙잡은 결함이 "눌러도 아무 반응이 없다"였다. 지금 구조는
서버가 다 뜬 뒤에야 브라우저가 열리므로, 그 전까지 화면에 아무것도
없다 - 무거운 import가 도는 십수 초 동안 사람은 실패와 구별할 수 없다.

그래서 순서를 뒤집는다. 창을 **먼저** 띄우고("시작하는 중"), 준비가
끝나면 그 창을 /studio 로 옮긴다. 실패하면 그 창에 왜 실패했는지를
적는다. 창이 먼저 있으므로 초기화 실패에도 할 말이 생긴다.

주의 - 이것은 "서버가 준비되기 전에 /studio 를 연다"와 다르다.
load_url 은 _wait_until_serving 이 참을 돌려준 뒤에만 부른다.

pywebview 는 이 저장소의 의존이 아니다
--------------------------------------
requirements.txt 에 넣지 않았다. 이번 Sprint 는 검증이고, 검증이
끝나기 전에 배포 의존을 늘리지 않는다. 없으면 없다고 말한다.

    python -m pip install --target <어딘가> pywebview
    set PYTHONPATH=<어딘가>
"""

import os
import socket
import sys
import threading
import time

HOST = "127.0.0.1"

WINDOW_TITLE = "AI영상제작소"

# 처음 열릴 창. 1366x768 화면에도 들어가야 한다 - 그보다 크게 잡으면
# 작은 노트북에서 창이 화면 밖으로 나간다.
WINDOW_SIZE = (1280, 800)

# 이보다 작게 줄이지 못하게 한다.
#
# Sprint222 - 1024 였는데 낮췄다. 1366x768 화면을 125% 로 쓰면 논리
# 데스크톱이 1093x614 이고, 작업 표시줄을 빼면 세로가 566 쯤이다.
# 최소를 640 으로 두면 그 PC 에서 창이 화면보다 커진다.
MIN_WINDOW_SIZE = (940, 520)


def _work_area():
    """
    작업 표시줄을 뺀 화면 크기. 못 구하면 None.

    왜 배율을 따로 안 나누는가
    --------------------------
    이 함수는 pywebview 가 SetProcessDPIAware 를 부르기 **전에** 불린다.
    그 전의 프로세스에게 Windows 는 화면을 이미 배율로 나눈 값으로
    말해 준다 - 1366x768 을 125% 로 쓰면 1093x614 라고 답한다. 그것이
    바로 pywebview 가 쓰는 단위라서, 여기서 다시 나누면 두 번 나뉜다.
    """

    if not sys.platform.startswith("win"):
        return None

    import ctypes
    from ctypes import wintypes

    SPI_GETWORKAREA = 0x0030

    rect = wintypes.RECT()

    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    except Exception:
        return None

    if not ok:
        return None

    width = rect.right - rect.left
    height = rect.bottom - rect.top

    return (width, height) if width > 0 and height > 0 else None


def initial_size():
    """
    첫 창 크기. 화면 밖으로 나가지 않는다.

    작은 화면에서 1280x800 을 고집하면 창의 오른쪽과 아래가 화면 밖으로
    나가고, 거기 있는 [영상 생성] 을 사람이 볼 수 없다.

    가장자리를 조금 남긴다 - 창이 작업 영역에 딱 붙으면 사람이 창을
    잡아 옮길 자리가 없다.
    """

    width, height = WINDOW_SIZE
    area = _work_area()

    if not area:
        return width, height

    margin = 40

    return (
        max(MIN_WINDOW_SIZE[0], min(width, area[0] - margin)),
        max(MIN_WINDOW_SIZE[1], min(height, area[1] - margin)),
    )

# 서버가 실제로 받을 때까지 기다리는 최대 시간. launcher 와 같은 값을
# 쓰되, 그쪽을 못 가져오면 이 값으로 선다.
READY_TIMEOUT_SECONDS = 90.0


def _launcher():
    """
    launcher.py 를 읽기 전용으로 가져온다. 못 가져오면 None.

    import 만 한다 - launcher.py 는 함수 정의뿐이고 __main__ 가드가
    있어서 들이는 것만으로는 아무 일도 일어나지 않는다(실측).
    """

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    try:
        import launcher

        return launcher
    except Exception:
        return None


def _free_port() -> int:
    """launcher 를 못 가져왔을 때만 쓰는 대체 경로."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))

        return sock.getsockname()[1]


def choose_port(preferred=None) -> int:
    """앉을 자리. launcher 의 규칙을 그대로 쓴다."""

    found = _launcher()

    if found is not None:
        return found.choose_port(preferred)

    return preferred if preferred else _free_port()


def _serving(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), 0.25):
            return True
    except OSError:
        return False


def wait_until_serving(port: int, timeout: float = None) -> bool:
    """
    서버가 실제로 받을 때까지 기다린다.

    launcher 의 _wait_until_serving 을 그대로 쓴다 - 그 함수가 붙잡은
    문제(시간을 재지 말고 실제로 받는지를 본다)는 여기서도 똑같다.
    """

    found = _launcher()

    if found is not None and hasattr(found, "_wait_until_serving"):
        return found._wait_until_serving(port, timeout)

    deadline = time.time() + (READY_TIMEOUT_SECONDS
                              if timeout is None else timeout)

    while time.time() < deadline:
        if _serving(port):
            return True

        time.sleep(0.2)

    return _serving(port)


def studio_url(port: int) -> str:
    """화면의 주소. 127.0.0.1 밖으로 나가지 않는다."""

    return f"http://{HOST}:{port}/studio"


class ServerThread:
    """
    기존 FastAPI 앱을 백그라운드에서 돌린다.

    왜 uvicorn.run 이 아닌가
    -----------------------
    uvicorn.run 은 메인 스레드를 블로킹하고 끄는 손잡이를 주지 않는다.
    창이 수명을 쥐는 구조에서는 메인 스레드가 GUI 것이어야 하고, 창이
    닫힐 때 서버에게 "그만"이라고 말할 수 있어야 한다.

    uvicorn.Server 를 직접 들면 should_exit 한 줄로 그 말을 할 수 있다.

    daemon 으로 둔다 - 이번 Sprint 는 종료 통합을 하지 않으므로, 서버가
    안 끝나서 창만 닫히고 프로세스가 남는 상태를 만들지 않는다.
    """

    def __init__(self, port: int):
        self.port = port
        self.server = None
        self.thread = None
        self.failure = None

    def start(self) -> None:
        import uvicorn

        from app.main import app

        config = uvicorn.Config(app, host=HOST, port=self.port,
                                log_level="warning")

        self.server = uvicorn.Server(config)

        def run():
            try:
                self.server.run()
            except BaseException as failed:
                self.failure = failed

        self.thread = threading.Thread(target=run, daemon=True,
                                       name="ai-studio-server")
        self.thread.start()

    def stop(self, timeout: float = 10.0) -> bool:
        """그만하라고 말하고 기다린다. 끝났으면 True."""

        if self.server is not None:
            self.server.should_exit = True

        if self.thread is None:
            return True

        self.thread.join(timeout)

        return not self.thread.is_alive()

    def alive(self) -> bool:
        return bool(self.thread and self.thread.is_alive())


# --- Sprint221 - 자식 프로세스의 수명 -----------------------------------

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9

# 만든 Job 을 붙잡아 둔다. 놓으면 핸들이 닫히고, 그 순간 규칙이 발동해
# 우리 자신까지 죽는다 - 반드시 프로세스가 사는 동안 살아 있어야 한다.
_job = None


def own_children() -> bool:
    """
    이 프로세스가 죽으면 자손도 함께 죽게 만든다. 성공하면 True.

    왜 필요한가
    -----------
    영상 렌더는 moviepy 가 ffmpeg 를 자식 프로세스로 띄워서 한다. 그런데
    이 저장소에는 그 자식을 붙잡아 두는 코드가 없다 - Popen 핸들을
    moviepy 가 제 안에 들고 있고, terminate/kill 을 부르는 곳이 없다(실측).

    지금까지는 그래도 됐다. 창(브라우저)과 서버(콘솔)가 따로였고, 서버를
    끄는 것은 사람이 콘솔을 닫는 일이었기 때문이다. Desktop Host 는
    창이 곧 프로세스다 - 창을 닫으면 파이썬은 사라지는데 ffmpeg 는
    남아서 CPU 를 먹는다. 사람 눈에는 "끈 프로그램이 컴퓨터를 느리게
    만든다" 로 보인다.

    Job Object 는 그 관계를 운영체제에 등록한다. 우리가 어떻게 죽든 -
    정상 종료든, 예외든, 작업 관리자에서 강제 종료든 - 자손이 함께
    정리된다. 파이썬 코드가 실행될 기회가 없는 죽음에서도 동작하는
    것이 핵심이다.

    실패해도 프로그램은 켜진다. 이미 다른 Job 에 들어 있는 자리(일부
    CI, 컨테이너)가 있을 수 있고, 그때 못 켜는 것은 과한 대가다.
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
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

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

    # restype 을 주지 않으면 64비트 핸들이 int 로 잘려 돌아온다. 잘린
    # 값으로는 뒤의 호출이 전부 실패하는데, 실패 이유가 "핸들이 이상하다"
    # 뿐이라 원인을 찾기 어렵다(Sprint221 에서 실제로 여기서 막혔다).
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,
                                                  wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    try:
        handle = kernel32.CreateJobObjectW(None, None)

        if not handle:
            return False

        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

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


def running_jobs() -> list:
    """
    지금 돌고 있는 작업들. 읽기만 한다.

    studio_jobs 를 고치지 않는다 - 이미 있는 recent() 로 충분하다.
    못 읽으면 빈 목록이다. 여기서 실패해서 창이 안 닫히면 안 된다.
    """

    try:
        from app.services import studio_jobs

        return [job for job in studio_jobs.recent(limit=500)
                if job.get("state") == "running"]
    except Exception:
        return []


def _describe(jobs) -> str:
    """무엇이 돌고 있는지 사람 말로. 이름을 대야 사람이 판단할 수 있다."""

    names = {"generate": "영상 만들기", "regenerate": "다시 만들기",
             "upload": "업로드", "oauth": "로그인", "social": "계정 연동"}

    lines = []

    for job in jobs[:5]:
        what = names.get(job.get("kind"), job.get("kind") or "작업")
        topic = (job.get("title") or job.get("topic") or "").strip()

        lines.append(f"    · {what}" + (f" - {topic[:40]}" if topic else ""))

    if len(jobs) > 5:
        lines.append(f"    · 그 밖에 {len(jobs) - 5}개")

    return "\n".join(lines)


def ask_before_closing(jobs) -> bool:
    """
    닫아도 되겠냐고 묻는다. 닫아도 되면 True.

    왜 JS 대화상자가 아닌가
    -----------------------
    이 함수는 창이 닫히는 순간 **UI 스레드에서** 불린다. 거기서
    evaluate_js 를 부르면 화면의 응답을 기다리는데, 그 화면을 그리는
    것이 바로 지금 멈춰 있는 그 스레드다 - 서로 기다리다 굳는다.

    그래서 운영체제의 대화상자를 쓴다. 새 의존도 필요 없다.
    """

    import ctypes

    MB_YESNO = 0x00000004
    MB_ICONWARNING = 0x00000030
    MB_SETFOREGROUND = 0x00010000
    MB_DEFBUTTON2 = 0x00000100  # 기본값을 [아니오] 로 - 실수로 지우지 않게
    IDYES = 6

    text = (f"아직 끝나지 않은 작업이 {len(jobs)}개 있습니다.\n\n"
            f"{_describe(jobs)}\n\n"
            "지금 닫으면 이 작업들은 중단되고, 만들던 영상은 남지 않습니다.\n"
            "그래도 닫으시겠습니까?")

    try:
        answer = ctypes.windll.user32.MessageBoxW(
            0, text, WINDOW_TITLE,
            MB_YESNO | MB_ICONWARNING | MB_SETFOREGROUND | MB_DEFBUTTON2)
    except Exception:
        return True  # 물어보지 못했다고 못 닫게 하면 창이 갇힌다

    return answer == IDYES


# --- Sprint222 - 화면이 부를 수 있는 것 하나 -----------------------------

# pywebview 의 FileDialog.FOLDER. 숫자를 적어 두는 이유는 이 파일이
# webview 를 최상단에서 들이지 않기 때문이다(없는 자리에서도 들어와야
# 한다). 값이 바뀌면 아래 pick_folder 가 조용히 다른 창을 열게 되므로
# tests/test_host_desktop.py 가 실제 상수와 대조한다.
FOLDER_DIALOG = 20


class Bridge:
    """
    화면과 이 프로그램 사이의 **좁은 문** 하나.

    여는 것은 폴더 선택 창뿐이다
    ----------------------------
    자료를 찾거나, 파일을 옮기거나, 프로젝트를 만들거나, 영상을 만드는
    일은 여기서 하지 않는다. 그런 것을 하나 넣기 시작하면 이 문은 두
    번째 API 가 되고, 그때부터 같은 기능이 서버와 브리지 두 곳에 살게
    된다 - 어느 날 한쪽만 고쳐진다.

    돌려주는 것은 고른 폴더의 절대 경로 하나. 취소하면 빈 문자열이다.
    (None 을 돌려주면 JS 쪽에서 "브리지가 없다"와 구별되지 않는다 -
    브라우저 모드로 잘못 떨어질 수 있다.)

    왜 필요한가
    -----------
    브라우저에는 폴더의 **경로**를 알려 주는 표준 API 가 없다.
    <input webkitdirectory> 는 파일 목록만 주고 절대 경로는 주지 않는데,
    free_workspace 가 기억하는 것은 경로다. 그래서 지금까지 화면은
    prompt() 로 사람에게 경로를 받아 적게 했다 - 데스크톱 앱에서 그것은
    할 일이 아니다.
    """

    def __init__(self):
        # 밑줄로 시작한다. pywebview 는 js_api 객체의 **인스턴스 속성까지**
        # 화면에 내보내므로, self.window 로 두면 창 객체가
        # window.pywebview.api.window 로 새어 나간다(실측: 문에 두 개가
        # 보였다). 문은 하나여야 한다.
        self._window = None

    def pick_folder(self, start: str = "") -> str:
        """
        폴더 선택 창을 연다. 고른 절대 경로, 취소하면 빈 문자열.

        절대 던지지 않는다 - 여기서 예외가 나면 화면 쪽 await 가 깨지고,
        사람은 창이 열리지도 닫히지도 않는 것을 본다.
        """

        if self._window is None:
            return ""

        try:
            picked = self._window.create_file_dialog(
                FOLDER_DIALOG, directory=str(start or ""))
        except Exception:
            return ""

        if not picked:
            return ""

        if isinstance(picked, (list, tuple)):
            return str(picked[0]) if picked else ""

        return str(picked)

    def open_folder(self, path: str = "") -> str:
        """
        탐색기로 그 폴더를 연다. 열었으면 "", 못 열었으면 이유 한 줄.

        왜 아무 데나 열지 않는가
        ------------------------
        이 문은 화면이 부른다. 화면이 부르는 값을 그대로 믿고 열면,
        어느 날 화면의 실수 하나로 이 프로그램이 남의 폴더를 여는
        도구가 된다. 그래서 **열어도 되는 자리인지 여기서 다시 본다** -
        부르는 쪽을 믿지 않는 것이 문의 일이다.

        열어도 되는 자리
        ----------------
            자료 폴더와 그 아래   free_workspace 가 기억한 root
            배경음악 자리        렌더가 실제로 보는 그 자리

        판정을 새로 만들지 않는다 - 두 자리 모두 이미 있는 것에게
        묻는다(free_workspace.remembered · runtime_paths.music_root).

        절대 던지지 않는다.
        """

        # 빈 값을 먼저 막는다.
        #
        # os.path.abspath("") 는 빈 문자열이 아니라 **지금 디렉터리**를
        # 돌려준다. 그래서 abspath 뒤에 비었는지 보면 그 검사는 영원히
        # 참이 되지 않고, 빈 경로가 조용히 현재 폴더로 해석된다(실측:
        # 화면에서 빈 값을 넘겼더니 저장소 폴더가 열렸다).
        raw = str(path or "").strip()

        if not raw:
            return "경로가 비어 있습니다."

        try:
            wanted = os.path.abspath(raw)
        except Exception:
            return "경로가 올바르지 않습니다."

        if not os.path.isdir(wanted):
            return "그런 폴더가 없습니다."

        if not self._allowed(wanted):
            return "이 프로그램이 쓰는 자료 폴더만 열 수 있습니다."

        try:
            os.startfile(wanted)          # noqa: S606 - Windows 탐색기
        except Exception as failed:
            return f"폴더를 열지 못했습니다: {failed}"

        return ""

    @staticmethod
    def _allowed(wanted: str) -> bool:
        """
        열어도 되는 자리인가.

        자리 목록을 여기서 짓지 않는다 - 지으면 어느 날 엔진이 보는
        자리와 달라진다.
        """

        roots = []

        try:
            from app.services import free_workspace

            remembered = free_workspace.remembered(
                free_workspace.default_store_path()) or {}
            root = remembered.get("root")

            if root:
                roots.append(root)
        except Exception:
            pass

        try:
            from app import runtime_paths

            roots.append(runtime_paths.music_root())
        except Exception:
            pass

        for root in roots:
            try:
                base = os.path.abspath(root)
            except Exception:
                continue

            if wanted == base or wanted.startswith(base + os.sep):
                return True

        return False


def _page(title: str, body: str) -> str:
    """창 안에 띄우는 안내 한 장. 바깥을 부르지 않는다."""

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{title}</title></head>
<body style="margin:0;background:#16181d;color:#e6e8ec;
font:15px/1.7 'Malgun Gothic',system-ui;display:flex;align-items:center;
justify-content:center;height:100vh">
<div style="max-width:640px;padding:32px">{body}</div>
</body></html>"""


SPLASH = _page("시작하는 중", """
<div style="font-size:19px;font-weight:600;margin-bottom:10px">AI영상제작소</div>
<div style="color:#8b929e">시작하는 중입니다. 처음 켤 때는 조금 걸립니다.</div>
""")


def failure_page(reason: str, detail: str = "") -> str:
    """
    켜지 못한 이유를 창 안에 적는다.

    이 함수가 이번 프로토타입에서 가장 값이 큰 부분이다 - 지금은 이
    문장들이 콘솔에만 있고, 콘솔은 다른 창 뒤에 있거나 사라진다.
    """

    extra = (f'<div style="margin-top:14px;color:#8b929e;font-size:13px;'
             f'white-space:pre-wrap">{detail}</div>') if detail else ""

    return _page("켜지 못했습니다", f"""
<div style="font-size:19px;font-weight:600;margin-bottom:10px;color:#e05561">
프로그램을 켜지 못했습니다</div>
<div>{reason}</div>{extra}
""")


def prepare_server(port: int = None):
    """
    서버를 띄우고 받을 때까지 기다린다.

    돌려주는 것은 (ServerThread, 주소, 실패이유) 세 개다. 실패이유가
    있으면 앞의 둘은 믿지 않는다.

    ffmpeg 를 먼저 본다 - launcher 가 그렇게 한다. moviepy 는 들이는
    순간 ffmpeg 를 찾고, 없으면 라이브러리의 RuntimeError 로 끝난다.
    그 문장에는 무엇을 어디에 넣으라는 말이 없다.
    """

    # 서버보다 먼저 한다. 서버가 뜨면 곧 렌더가 시작될 수 있고, 그때
    # 태어나는 ffmpeg 는 이미 우리 Job 안에 있어야 한다.
    if not own_children():
        print("  [알림] 자식 프로세스 정리 규칙을 걸지 못했습니다. "
              "창을 닫아도 ffmpeg 가 남을 수 있습니다.")

    found = _launcher()

    if found is not None:
        try:
            found._prepare_home()
        except Exception:
            pass

        if found.use_our_ffmpeg() is None:
            return None, None, ("ffmpeg 가 없어 시작할 수 없습니다. "
                                "프로그램 옆 tools 폴더에 ffmpeg.exe 를 "
                                "넣고 다시 켜십시오.")

    chosen = choose_port(port)

    server = ServerThread(chosen)

    try:
        server.start()
    except BaseException as failed:
        return None, None, f"서버를 시작하지 못했습니다.\n{type(failed).__name__}: {failed}"

    if not wait_until_serving(chosen):
        detail = ""

        if server.failure is not None:
            detail = f"{type(server.failure).__name__}: {server.failure}"

        return server, None, ("서버가 응답하지 않습니다." +
                              (f"\n{detail}" if detail else ""))

    return server, studio_url(chosen), None


def _bootstrap(window, port):
    """
    창이 뜬 뒤 백그라운드에서 도는 부분.

    pywebview 가 이 함수를 제 스레드에서 부른다 - 메인 스레드는 GUI
    루프의 것이므로 여기서 무거운 일을 한다.
    """

    server, url, reason = prepare_server(port)

    if reason:
        window.load_html(failure_page(reason))

        return server

    print(f"  주소   {url}")
    sys.stdout.flush()

    window.load_url(url)

    return server


def shutdown(server) -> bool:
    """
    창이 닫힌 뒤의 정리. 순서가 뜻이다.

        1. uvicorn 에게 그만하라고 말하고 기다린다
        2. 프로세스가 끝나면 Job 이 닫히고 ffmpeg 자손이 함께 정리된다

    2번을 우리가 직접 하지 않는 이유는, 우리가 직접 할 수 있는 죽음만
    처리하면 정작 무서운 죽음(강제 종료)에서 아무것도 못 하기 때문이다.
    운영체제에 맡기면 모든 죽음에서 같은 일이 일어난다.
    """

    if server is None:
        return True

    stopped = server.stop()

    print(f"  서버 종료 {'완료' if stopped else '미완료(스레드 잔존)'}")

    if _job is not None:
        print("  자식 프로세스는 이 프로세스가 끝나는 순간 함께 정리됩니다.")

    sys.stdout.flush()

    return stopped


def run_window(port: int = None, debug: bool = False,
               confirm_close: bool = False) -> int:
    """창을 띄운다. 창이 닫히면 돌아온다."""

    try:
        import webview
    except ImportError:
        print()
        print("  pywebview 가 없어 창을 띄울 수 없습니다.")
        print("  이 저장소의 의존이 아닙니다(검증이 끝나기 전에 배포")
        print("  의존을 늘리지 않습니다). 따로 두고 가리키십시오:")
        print()
        print("    python -m pip install --target <어딘가> pywebview")
        print("    set PYTHONPATH=<어딘가>")
        print()

        return 1

    holder = {}

    width, height = initial_size()

    # 화면이 부를 수 있는 좁은 문. 폴더 선택 하나뿐이다.
    bridge = Bridge()

    window = webview.create_window(
        WINDOW_TITLE,
        html=SPLASH,
        js_api=bridge,
        width=width, height=height,
        min_size=MIN_WINDOW_SIZE,
        resizable=True,
        background_color="#16181d",
        # 아무것도 안 하고 있을 때까지 물어보면 사람은 곧 읽지 않고
        # 누른다. 물어보는 것은 잃을 것이 있을 때뿐이다(아래 on_closing).
        confirm_close=confirm_close,
    )

    def on_closing():
        """
        닫아도 되는가. False 를 돌려주면 창이 닫히지 않는다.

        pywebview 는 closing 만 잠금(동기) 이벤트로 만들어 두었다
        (webview/window.py: Event(self, True)). 그래서 여기서 돌려주는
        False 가 실제로 창을 붙잡는다 - 다른 이벤트였다면 핸들러가
        끝나기도 전에 창이 닫힌다.
        """

        jobs = running_jobs()

        if not jobs:
            return True

        allowed = ask_before_closing(jobs)

        if not allowed:
            print(f"  닫기를 취소했습니다 (작업 {len(jobs)}개 진행 중)")
            sys.stdout.flush()

        return allowed

    bridge._window = window

    window.events.closing += on_closing

    def boot(win):
        holder["server"] = _bootstrap(win, port)

    # gui="edgechromium" 를 못 박지 않는다. 못 박으면 WebView2 런타임이
    # 없는 PC 에서 pywebview 자신의 오류로 끝나고, 우리가 할 말이 없다.
    # 무엇으로 떴는지는 아래에서 확인한다.
    webview.start(boot, window, debug=debug)

    shutdown(holder.get("server"))

    return 0


def run_check(port: int = None) -> int:
    """
    창 없이 서버 길만 확인한다.

    창을 띄우지 못하는 자리(CI, 원격 세션)에서도 "서버는 뜨는가"를
    가릴 수 있어야 한다. GUI 가 없다고 아무것도 못 재는 것은 곤란하다.
    """

    server, url, reason = prepare_server(port)

    if reason:
        print(f"  FAIL  {reason}")

        return 1

    print(f"  OK    {url}")

    try:
        from urllib.request import urlopen

        for path in ("/health", "/studio"):
            with urlopen(f"http://{HOST}:{server.port}{path}", timeout=10) as r:
                print(f"  OK    {path}  {r.status}  {len(r.read())} bytes")
    except Exception as failed:
        print(f"  FAIL  {type(failed).__name__}: {failed}")

        server.stop()

        return 1

    stopped = shutdown(server)

    return 0 if stopped else 1


def asked_port(argv) -> int:
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


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    port = asked_port(argv)

    if "--check" in argv:
        return run_check(port)

    return run_window(port, debug="--debug" in argv,
                      confirm_close="--confirm-close" in argv)


if __name__ == "__main__":
    raise SystemExit(main())
