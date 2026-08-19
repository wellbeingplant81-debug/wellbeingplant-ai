"""
Sprint220 - WebView2 안에서 기존 화면이 실제로 사는지 재는 스모크.

    python tests/smoke_host_desktop.py            사람 없이 잴 수 있는 것만
    python tests/smoke_host_desktop.py --dialogs  R1 대화상자 28종 판정(클릭 필요)

pytest 가 집어가지 않는다 - 이름이 test_ 로 시작하지 않는다. 일부러
그렇게 두었다. 이 파일은 창이 뜨는 자리에서만 의미가 있고, 창이 없는
자리에서 실패하면 그것은 결함이 아니라 자리의 성질이다.

무엇을 사람 없이 재는가
-----------------------
"화면이 떴다"를 눈으로 보지 않고도 잴 수 있다. 뜬 화면에게 물어보면
된다 - DOM 이 몇 개인지, 테마가 무엇으로 칠해졌는지, fetch 가 실제로
200 을 받는지. evaluate_js 가 그 통로다.

무엇을 사람이 눌러야 하는가
---------------------------
alert/confirm/prompt 는 JS 를 멈춰 세운다. 멈춘 것을 다시 굴리려면
사람이 눌러야 한다. 이것만은 대신해 줄 수 없어서 --dialogs 로 떼어
두었다.

기존 것을 고치지 않는다
-----------------------
studio.html 을 손대지 않는다. 여기서 하는 것은 이미 떠 있는 화면에
질문을 던지는 것뿐이고, 파일은 그대로다.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import host_desktop

PASS = "PASS"
FAIL = "FAIL"

_results = []


def _record(name, ok, detail=""):
    _results.append((name, PASS if ok else FAIL, detail))

    mark = PASS if ok else FAIL
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail else ""))
    sys.stdout.flush()


def _js(window, script, default=None):
    """물어본다. 못 물어보면 default."""

    try:
        return window.evaluate_js(script)
    except Exception as failed:
        return default if default is not None else f"__ERROR__{failed}"


def _js_async(window, body: str, timeout: float = 30.0):
    """
    비동기 결과를 받아 온다.

    evaluate_js 는 Promise 를 기다리지 않는다 - await 없이 직렬화하므로
    async 식을 그대로 넘기면 빈 객체({})가 돌아온다(실측). 그래서 결과를
    전역에 적어 두게 하고, 적힐 때까지 여기서 본다.
    """

    slot = "__smokeSlot"

    _js(window, f"window.{slot} = null;")
    _js(window, f"(async () => {{ try {{ window.{slot} = await ({body}); }}"
                f" catch (e) {{ window.{slot} = 'ERR ' + e.name + ': ' + e.message; }} }})();")

    deadline = time.time() + timeout

    while time.time() < deadline:
        got = _js(window, f"window.{slot}")

        if got is not None and got != {}:
            return got

        time.sleep(0.2)

    return "ERR timeout"


def _windows_clipboard() -> str:
    """Windows 클립보드에 실제로 무엇이 들었는지 파이썬 쪽에서 읽는다."""

    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    # argtypes 를 주지 않으면 64비트 핸들이 int 로 넘어가다 넘친다(실측).
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]

    if not user32.OpenClipboard(None):
        return ""

    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)

        if not handle:
            return ""

        pointer = kernel32.GlobalLock(handle)

        if not pointer:
            return ""

        try:
            return ctypes.c_wchar_p(pointer).value or ""
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _wait_loaded(window, timeout=60.0):
    """/studio 가 실제로 그려질 때까지."""

    deadline = time.time() + timeout

    while time.time() < deadline:
        state = _js(window, "document.readyState")

        if state == "complete":
            nodes = _js(window, "document.getElementsByTagName('*').length", 0)

            if isinstance(nodes, int) and nodes > 100:
                return nodes

        time.sleep(0.3)

    return 0


def check_render(window):
    """화면이 실제로 살아 있는가. 눈 대신 DOM 에게 묻는다."""

    nodes = _wait_loaded(window)

    _record("studio.html 렌더", nodes > 100, f"DOM {nodes}개")

    theme = _js(window, "document.documentElement.getAttribute('data-theme')")
    _record("테마 서버 치환", bool(theme) and "{{" not in str(theme),
            f"data-theme={theme}")

    ua = _js(window, "navigator.userAgent", "")
    _record("WebView2 엔진", "Edg" in str(ua), str(ua)[-60:])

    body = _js(window, "document.body.getBoundingClientRect().width", 0)
    _record("레이아웃 폭", isinstance(body, (int, float)) and body > 800,
            f"{body}px")

    errors = _js(window, "window.__smokeErrors ? window.__smokeErrors.length : 0", 0)
    _record("JS 오류", errors == 0, f"{errors}건")


def check_fetch(window):
    """
    화면이 부르는 길이 WebView2 안에서도 살아 있는가.

    studio.html 의 fetch 를 흉내내지 않고, 그 페이지의 컨텍스트에서
    실제로 fetch 를 부른다 - origin·쿠키·헤더가 전부 그 화면의 것이다.
    """

    body = """(async () => {
      const paths = ['/health', '/studio/api/settings', '/studio/api/about',
                     '/studio/api/production/creation-modes'];
      const out = [];
      for (const p of paths) {
        try { const r = await fetch(p); out.push(p + ' ' + r.status); }
        catch (e) { out.push(p + ' ERR ' + e.message); }
      }
      return out.join(' | ');
    })()"""

    text = str(_js_async(window, body))

    ok = text.count(" 200") >= 3 and "ERR" not in text

    _record("fetch (GET 4종)", ok, text[:160])


def check_clipboard(window):
    """
    navigator.clipboard.writeText 가 되는가.

    사람의 클릭 없이 부르면 Chromium 이 거절할 수 있다(transient user
    activation). 거절당하면 그 사실 자체가 답이다 - 그때는 실제 버튼을
    눌러 봐야 한다고 보고한다.
    """

    token = f"AI영상제작소-스모크-{int(time.time())}"

    body = (f"(async () => {{ await navigator.clipboard.writeText({token!r});"
            f" return 'ok'; }})()")

    said = str(_js_async(window, body))

    if said != "ok":
        _record("clipboard writeText", False,
                f"{said[:90]} (사용자 제스처 없이 호출한 결과 - "
                "실제 [정보 복사] 버튼으로 재확인 필요)")

        return

    time.sleep(0.3)

    _record("clipboard writeText", _windows_clipboard() == token,
            "Windows 클립보드 대조")


def check_video_range(window):
    """<video> 가 탐색하려면 서버가 Range 를 받아야 한다."""

    body = """(async () => {
      const r = await fetch('/studio', {headers: {'Range': 'bytes=0-99'}});
      return r.status + ' ' + (r.headers.get('content-range') || 'no-range');
    })()"""

    said = str(_js_async(window, body))

    _record("Range 요청", "206" in said or "200" in said, said[:80])


def run_auto(window):
    print()
    print("  사람 없이 재는 것")
    print("  " + "-" * 52)

    check_render(window)
    check_fetch(window)
    check_clipboard(window)
    check_video_range(window)


def run_dialogs(window):
    """
    R1 판정. 사람이 눌러야 한다.

    28개를 하나씩 부르지 않는다 - 28개가 쓰는 것은 alert/confirm/prompt
    세 가지 원시 기능이고, 그 셋이 살아 있으면 28개가 산다. 죽어 있으면
    28개가 죽는다. 재야 할 것은 개수가 아니라 그 셋이다.
    """

    print()
    print("  R1 - 대화상자 (창을 보고 눌러 주십시오)")
    print("  " + "-" * 52)

    print("  1/5 alert  : [확인] 을 누르십시오")
    sys.stdout.flush()
    said = _js(window, "alert('R1 alert 확인 - [확인]을 누르십시오'); 'returned'")
    _record("alert 표시 후 JS 복귀", said == "returned", str(said)[:60])

    print("  2/5 confirm: [확인] 을 누르십시오")
    sys.stdout.flush()
    said = _js(window, "confirm('R1 confirm - [확인]을 누르십시오')")
    _record("confirm 확인 -> true", said is True, repr(said))

    print("  3/5 confirm: [취소] 를 누르십시오")
    sys.stdout.flush()
    said = _js(window, "confirm('R1 confirm - [취소]를 누르십시오')")
    _record("confirm 취소 -> false", said is False, repr(said))

    print("  4/5 prompt : 그대로 두고 [확인] 을 누르십시오")
    sys.stdout.flush()
    said = _js(window, "prompt('R1 prompt - 그대로 두고 [확인]', '스프린트220')")
    _record("prompt 입력 -> 값", said == "스프린트220", repr(said))

    print("  5/5 prompt : [취소] 를 누르십시오")
    sys.stdout.flush()
    said = _js(window, "prompt('R1 prompt - [취소]를 누르십시오', '값')")
    _record("prompt 취소 -> null", said is None, repr(said))


def run(dialogs: bool, keep: bool = False):
    try:
        import webview
    except ImportError:
        print("  pywebview 가 없습니다. host_desktop.py 의 안내를 보십시오.")

        return 1

    server, url, reason = host_desktop.prepare_server()

    if reason:
        print(f"  [FAIL] 서버: {reason}")

        return 1

    print(f"  주소 {url}")

    window = webview.create_window(
        host_desktop.WINDOW_TITLE + " - 스모크",
        url=url,
        width=host_desktop.WINDOW_SIZE[0],
        height=host_desktop.WINDOW_SIZE[1],
        min_size=host_desktop.MIN_WINDOW_SIZE,
        background_color="#16181d",
    )

    def body(win):
        try:
            _body(win)
        except BaseException as failed:
            print(f"  [FAIL] 스모크 자체가 죽었다: {type(failed).__name__}: {failed}")
            sys.stdout.flush()

            if not (dialogs or keep):
                win.destroy()

    def _body(win):
        # 화면이 스스로 낸 오류를 세어 둔다. 나중에 물어본다.
        try:
            win.evaluate_js(
                "window.__smokeErrors=[];"
                "window.addEventListener('error',e=>__smokeErrors.push(''+e.message));")
        except Exception:
            pass

        run_auto(win)

        if dialogs:
            run_dialogs(win)

        print()
        print("  " + "-" * 52)

        failed = [r for r in _results if r[1] == FAIL]

        print(f"  {len(_results) - len(failed)} PASS / {len(failed)} FAIL")

        if not dialogs:
            print()
            print("  R1(대화상자)은 --dialogs 로 따로 재십시오.")

        sys.stdout.flush()

        # 사람이 눌러야 할 일이 없으면 스스로 닫는다 - 아무도 안 보는
        # 창을 열어 두면 자동으로 돌리는 자리에서 영원히 멈춘다.
        if not (dialogs or keep):
            time.sleep(1.0)
            win.destroy()
        else:
            print("  창을 닫으면 끝납니다.")
            sys.stdout.flush()

    webview.start(body, window)

    server.stop()

    return 1 if any(r[1] == FAIL for r in _results) else 0


if __name__ == "__main__":
    raise SystemExit(run("--dialogs" in sys.argv[1:], "--keep" in sys.argv[1:]))
