"""
Sprint219 - 켜지지 않았을 때 무엇이 남는가 (Epic 63).

이 스위트가 생긴 이유
---------------------
사용자가 바탕화면 아이콘을 두 번 눌렀는데 아무 반응이 없었다. 그런데
프로그램이 남긴 것은 **아무것도 없었다** - 스물네 번 켜는 동안 logs
폴더는 만들어진 적조차 없다(실측). 그래서 우리도 사용자도 무엇이
잘못됐는지 알 방법이 없었다.

자취를 logs/ 에 두지 않는 이유
------------------------------
logs/ 는 "무언가 잘못됐다"는 뜻으로 지켜 온 자리다 - 잘 켜졌을 때는
만들지도 않는다(test_rc_final_check 가 그것을 붙잡고 있다). 켤 때마다
남기는 자취를 거기 두면 그 뜻이 사라진다. 그래서 자취는 .dataset 에
두고, 죽을 때만 오류 기록에 함께 붙인다 - 사람이 보내 주는 것은
그 파일 하나이기 때문이다.

여기서 지키는 것 셋
-------------------
    1. 켜는 동안 어디까지 왔는지 남는다        조용히 죽지 않는다
    2. 브라우저가 서버보다 먼저 열리지 않는다   죽은 주소를 열지 않는다
    3. 실패했을 때 창이 사라지지 않는다        적어 놓은 것을 읽을 시간

특히 2번이 이번에 찾은 실제 결함이다. 예전에는 1.5초를 세고 브라우저를
열었는데, 그 1.5초 뒤에 오는 것이 이 프로그램에서 가장 무거운 import
두 줄이다. 찬 PC에서는 그것이 1.5초를 넘고, 브라우저는 아직 아무도
듣지 않는 주소를 연다.
"""

import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launcher


class _Listener:
    """잠시 뒤에 열리는 자리. 느리게 뜨는 서버의 대역이다."""

    def __init__(self, delay: float):
        self.delay = delay
        self.port = None
        self._sock = None
        self._thread = None

    def __enter__(self):
        # 포트를 먼저 잡아 두었다가 놓고, delay 뒤에 실제로 듣는다.
        probe = socket.socket()
        probe.bind((launcher.HOST, 0))
        self.port = probe.getsockname()[1]
        probe.close()

        def later():
            time.sleep(self.delay)
            self._sock = socket.socket()
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._sock.bind((launcher.HOST, self.port))
                self._sock.listen(5)
            except OSError:
                pass

        self._thread = threading.Thread(target=later, daemon=True)
        self._thread.start()

        return self

    def __exit__(self, *exc):
        if self._sock:
            self._sock.close()


# ══ 1. 켜는 동안 자취를 남긴다 ══════════════════════════════════════

class TheStartupLeavesATrailTest(unittest.TestCase):

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)

        patcher = patch.dict(
            os.environ, {"AI_STUDIO_HOME": self.home.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _lines(self):
        path = os.path.join(self.home.name, launcher.TRAIL_DIRNAME, launcher.STARTUP_LOG)

        if not os.path.exists(path):
            return []

        with open(path, encoding="utf-8") as f:
            return f.readlines()

    def test_a_note_is_written(self):
        launcher.note("여기까지 왔다")

        self.assertTrue(
            any("여기까지 왔다" in line for line in self._lines()))

    def test_every_note_carries_a_time(self):
        launcher.note("무엇인가")

        said = self._lines()[-1]

        # 2026-08-18 08:07:02  무엇인가
        self.assertRegex(said, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s")

    def test_notes_accumulate(self):
        for i in range(5):
            launcher.note(f"걸음 {i}")

        self.assertEqual(len(self._lines()), 5)

    def test_the_file_does_not_grow_forever(self):
        for i in range(launcher.STARTUP_LOG_MAX_LINES + 60):
            launcher.note(f"걸음 {i}")

        lines = self._lines()

        self.assertLessEqual(len(lines), launcher.STARTUP_LOG_MAX_LINES + 1)
        # 최근 것이 남아야 한다 - 알고 싶은 것은 마지막 실행이다.
        self.assertIn(f"걸음 {launcher.STARTUP_LOG_MAX_LINES + 59}",
                      lines[-1])

    def test_a_broken_log_place_never_stops_the_program(self):
        """
        관찰이 제품을 멈추게 하면 관찰을 켠 것이 잘못이 된다.
        """

        with patch.object(launcher, "_trail_dir", return_value="Z:\\없는곳"):
            launcher.note("적히지 않아도 된다")   # 던지면 실패다

    def test_it_writes_even_when_the_app_package_is_unavailable(self):
        """
        이 기록이 존재하는 이유가 "app 패키지가 안 올라와도 이유를
        남긴다"이다. 그 상황에서 입을 다물면 아무 소용이 없다.
        """

        def no_app(name, *args, **kwargs):
            if name.startswith("app"):
                raise ImportError("app 이 없다")

            return _real_import(name, *args, **kwargs)

        _real_import = __import__

        with patch("builtins.__import__", side_effect=no_app):
            where = launcher._trail_dir()

        self.assertTrue(where)
        self.assertIn(self.home.name, where)


# ══ 2. 브라우저가 서버보다 먼저 열리지 않는다 ═══════════════════════

class TheBrowserWaitsForTheServerTest(unittest.TestCase):
    """이번에 찾은 실제 결함."""

    def test_it_reports_a_closed_port_as_not_serving(self):
        probe = socket.socket()
        probe.bind((launcher.HOST, 0))
        port = probe.getsockname()[1]
        probe.close()

        self.assertFalse(launcher._serving(port))

    def test_it_reports_an_open_port_as_serving(self):
        with _Listener(delay=0) as listener:
            time.sleep(0.3)

            self.assertTrue(launcher._serving(listener.port))

    def test_it_waits_for_a_slow_server(self):
        """
        1.5초를 세는 것으로는 못 고친다 - 빠른 PC에서는 그만큼
        늦어지고 느린 PC에서는 여전히 모자란다.
        """

        with _Listener(delay=0.8) as listener:
            started = time.monotonic()
            came_up = launcher._wait_until_serving(listener.port, timeout=8)
            waited = time.monotonic() - started

        self.assertTrue(came_up)
        self.assertGreater(waited, 0.5, "기다리지 않았다")

    def test_it_gives_up_on_a_server_that_never_comes(self):
        probe = socket.socket()
        probe.bind((launcher.HOST, 0))
        port = probe.getsockname()[1]
        probe.close()

        started = time.monotonic()
        came_up = launcher._wait_until_serving(port, timeout=0.6)

        self.assertFalse(came_up)
        self.assertLess(time.monotonic() - started, 4)

    def test_the_browser_opens_only_after_the_port_answers(self):
        """이 시험이 곧 이번 결함의 재현이다."""

        opened_at = []

        with _Listener(delay=1.0) as listener:
            with patch.object(launcher.webbrowser, "open",
                              side_effect=lambda u: opened_at.append(
                                  time.monotonic()) or True):
                started = time.monotonic()
                thread = launcher._open_browser(
                    "http://x/studio", ready_port=listener.port)
                thread.join(timeout=10)

        self.assertTrue(opened_at, "브라우저를 아예 안 열었다")
        self.assertGreater(
            opened_at[0] - started, 0.7,
            "서버가 뜨기도 전에 열었다 - 사람은 '연결할 수 없음'을 본다")

    def test_a_dead_address_is_not_opened(self):
        """
        여는 것이 "안 된다"고 잘못 가르치는 것보다, 아직 준비 중이라고
        말하는 편이 낫다.
        """

        probe = socket.socket()
        probe.bind((launcher.HOST, 0))
        port = probe.getsockname()[1]
        probe.close()

        said = []

        with patch.object(launcher, "WAIT_FOR_SERVER_SECONDS", 0.5), \
                patch.object(launcher.webbrowser, "open") as opened, \
                patch("builtins.print",
                      lambda *a, **k: said.append(
                          " ".join(str(x) for x in a))):
            thread = launcher._open_browser("http://x/studio",
                                            ready_port=port)
            thread.join(timeout=10)

        opened.assert_not_called()
        self.assertTrue(any("주소" in line for line in said),
                        f"주소를 알려 주지 않았다: {said}")

    def test_without_a_port_it_behaves_as_before(self):
        """
        포트를 모르면 기다릴 방법이 없다 - 예전 그대로다. 기존 가드가
        이 길을 쓴다.
        """

        opened = []

        with patch.object(launcher, "OPEN_AFTER_SECONDS", 0), \
                patch.object(launcher.webbrowser, "open",
                             side_effect=lambda u: opened.append(u) or True):
            thread = launcher._open_browser("http://x/studio")
            thread.join(timeout=5)

        self.assertEqual(opened, ["http://x/studio"])

    def test_a_refused_browser_still_tells_the_address(self):
        """webbrowser.open 은 실패를 False 로 돌려주기도 한다."""

        said = []

        with _Listener(delay=0) as listener:
            time.sleep(0.3)

            with patch.object(launcher.webbrowser, "open",
                              return_value=False), \
                    patch("builtins.print",
                          lambda *a, **k: said.append(
                              " ".join(str(x) for x in a))):
                thread = launcher._open_browser(
                    "http://x/studio", ready_port=listener.port)
                thread.join(timeout=10)

        self.assertTrue(any("주소" in line for line in said), said)


class TheTrailGoesToTheHouseWeStartedInTest(unittest.TestCase):
    """
    Sprint224 - 늦게 적는 자리 하나가 엉뚱한 집에 적고 있었다.

    이 스레드는 서버를 최대 90초 기다린 뒤에야 적는다. 그 안에서
    자리를 다시 구하면 그 사이에 바뀐 자리에 적힌다.

    실제로 회귀에서 걸렸다 - 이 스레드가 90초 뒤 깨어나 **다른
    시험의 임시 집**에 .dataset을 만들었고, "읽어 보는 것만으로
    아무것도 생기면 안 된다"는 시험이 그것을 잡았다
    (test_script_input_contract).
    """

    def _trail(self, home):
        return os.path.join(home, launcher.TRAIL_DIRNAME,
                            launcher.STARTUP_LOG)

    def test_a_late_note_lands_where_it_was_born(self):
        first = tempfile.TemporaryDirectory()
        second = tempfile.TemporaryDirectory()
        self.addCleanup(first.cleanup)
        self.addCleanup(second.cleanup)

        probe = socket.socket()
        probe.bind((launcher.HOST, 0))
        port = probe.getsockname()[1]
        probe.close()

        with patch.object(launcher, "WAIT_FOR_SERVER_SECONDS", 0.5), \
                patch("builtins.print", lambda *a, **k: None):

            with patch.dict(os.environ, {"AI_STUDIO_HOME": first.name}):
                thread = launcher._open_browser("http://x/studio",
                                                ready_port=port)

            # 스레드가 아직 기다리는 동안 집이 바뀐다.
            with patch.dict(os.environ, {"AI_STUDIO_HOME": second.name}):
                thread.join(timeout=10)

        self.assertTrue(os.path.exists(self._trail(first.name)),
                        "켠 집에 자취가 없다")
        self.assertFalse(os.path.exists(self._trail(second.name)),
                         "바뀐 집에 자취가 남았다")

    def test_the_changed_house_gets_nothing_at_all(self):
        """
        파일 하나가 아니라 폴더조차 생기면 안 된다 - 걸린 시험이 본
        것이 "무엇이 생겼는가"였다.
        """

        first = tempfile.TemporaryDirectory()
        second = tempfile.TemporaryDirectory()
        self.addCleanup(first.cleanup)
        self.addCleanup(second.cleanup)

        probe = socket.socket()
        probe.bind((launcher.HOST, 0))
        port = probe.getsockname()[1]
        probe.close()

        with patch.object(launcher, "WAIT_FOR_SERVER_SECONDS", 0.5), \
                patch("builtins.print", lambda *a, **k: None):

            with patch.dict(os.environ, {"AI_STUDIO_HOME": first.name}):
                thread = launcher._open_browser("http://x/studio",
                                                ready_port=port)

            with patch.dict(os.environ, {"AI_STUDIO_HOME": second.name}):
                thread.join(timeout=10)

        self.assertEqual(os.listdir(second.name), [])

    def test_the_note_still_writes_where_it_is_told(self):
        """where를 주지 않으면 예전 그대로 지금 집에 적는다."""

        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)

        with patch.dict(os.environ, {"AI_STUDIO_HOME": home.name}):
            launcher.note("여기까지 왔다")

        self.assertTrue(os.path.exists(self._trail(home.name)))


# ══ 3. 실패했을 때 창이 사라지지 않는다 ═════════════════════════════

class TheWindowDoesNotVanishTest(unittest.TestCase):

    def test_a_failed_start_holds_the_window(self):
        held = []

        with patch.object(launcher, "_serve", return_value=1), \
                patch.object(launcher, "_hold_console",
                             side_effect=lambda argv: held.append(True)):
            code = launcher.main([])

        self.assertEqual(code, 1)
        self.assertTrue(held, "창이 그냥 사라졌다")

    def test_a_good_start_does_not_hold(self):
        held = []

        with patch.object(launcher, "_serve", return_value=0), \
                patch.object(launcher, "_hold_console",
                             side_effect=lambda argv: held.append(True)):
            code = launcher.main([])

        self.assertEqual(code, 0)
        self.assertFalse(held, "정상 종료인데 붙잡았다")

    def test_a_crash_holds_the_window_too(self):
        held = []

        with patch.object(launcher, "_serve",
                          side_effect=RuntimeError("터졌다")), \
                patch.object(launcher, "_hold_console",
                             side_effect=lambda argv: held.append(True)), \
                patch("builtins.print"):
            code = launcher.main([])

        self.assertEqual(code, 1)
        self.assertTrue(held)

    def test_automation_is_never_held(self):
        """
        붙잡으면 자동으로 돌리는 자리가 영원히 멈춘다.
        """

        with patch.object(launcher.sys, "stdin", None):
            launcher._hold_console([])       # 던지지도, 멈추지도 않는다

        launcher._hold_console(["--no-hold"])

    def test_ctrl_c_is_not_a_failure(self):
        held = []

        with patch.object(launcher, "_serve",
                          side_effect=KeyboardInterrupt), \
                patch.object(launcher, "_hold_console",
                             side_effect=lambda argv: held.append(True)):
            code = launcher.main([])

        self.assertEqual(code, 0)
        self.assertFalse(held)


class TheTrailCoversTheWholeStartTest(unittest.TestCase):
    """켜는 길의 각 걸음이 실제로 기록되는가."""

    def test_the_steps_are_noted(self):
        import ast

        with open(launcher.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        noted = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "note"
            and node.args and isinstance(node.args[0], ast.Constant)
        }

        # 무거운 import 앞뒤가 갈라져 있어야, 거기서 멈춘 것을 알 수 있다.
        self.assertTrue(
            any("importing uvicorn" in s for s in noted),
            f"가장 무거운 자리 앞에 표식이 없다: {noted}")
        self.assertTrue(any("engine imported" in s for s in noted))
        self.assertTrue(any("ffmpeg" in s for s in noted))

    def test_main_notes_the_exit_reason(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)

        with patch.dict(os.environ, {"AI_STUDIO_HOME": home.name}), \
                patch.object(launcher, "_serve", return_value=1), \
                patch.object(launcher, "_hold_console"):
            launcher.main([])

        path = os.path.join(home.name, launcher.TRAIL_DIRNAME, launcher.STARTUP_LOG)

        with open(path, encoding="utf-8") as f:
            said = f.read()

        self.assertIn("launch", said)
        self.assertIn("exit: code 1", said)

    def test_a_good_start_leaves_no_logs_folder(self):
        """
        logs/ 는 "무언가 잘못됐다"는 뜻이다. 잘 켜졌는데 그 폴더가
        생겨 있으면 받은 사람은 무슨 일이 있었나 하게 된다.
        """

        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)

        with patch.dict(os.environ, {"AI_STUDIO_HOME": home.name}), \
                patch("uvicorn.run"):
            launcher.main(["--no-browser"])

        self.assertFalse(os.path.exists(os.path.join(home.name, "logs")))
        # 자취는 그래도 남아 있어야 한다.
        self.assertTrue(os.path.exists(
            os.path.join(home.name, launcher.TRAIL_DIRNAME,
                         launcher.STARTUP_LOG)))

    def test_a_crash_carries_the_trail_into_the_error_log(self):
        """
        README 는 "logs 폴더의 파일을 보내 주십시오"라고 말한다.
        보내 준 그 하나에 어디까지 갔었는지도 들어 있어야 한다.
        """

        from app import error_log

        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)

        with patch.dict(os.environ, {"AI_STUDIO_HOME": home.name}), \
                patch("uvicorn.run", side_effect=RuntimeError("엔진이 죽었다")), \
                patch.object(launcher, "_hold_console"), \
                patch("builtins.print"):
            launcher.main(["--no-browser"])

        where = os.path.join(home.name, error_log.DIRNAME)
        written = [n for n in os.listdir(where) if n.startswith("error-")]

        self.assertEqual(len(written), 1)

        with open(os.path.join(where, written[0]), encoding="utf-8") as f:
            said = f.read()

        self.assertIn("엔진이 죽었다", said)
        self.assertIn("자취", said)
        self.assertIn("importing uvicorn", said)


if __name__ == "__main__":
    unittest.main()
