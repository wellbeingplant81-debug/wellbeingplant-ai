"""
끄면 정말 끝난다 (Sprint230 뒷마무리).

무엇이 있었나
-------------
묶은 프로그램은 프로세스가 둘이다. PyInstaller 의 부트로더가 자식을
하나 띄우고 **서버는 그 자식**이다.

    부트로더 44348  ->  자식 29428 (uvicorn)

부트로더를 강제로 끝내면 자식이 남는다. 실측: 부모를 죽인 뒤 3초가
지나도 자식이 살아 있고 포트도 잡고 있었다. 그렇게 쌓인 것이 여섯
개였고, 그중 하나가 dist 의 exe 를 물고 있어서 다음 묶기가
WinError 5 로 죽었다.

사람이 창을 닫거나 Ctrl+C 를 누르면 콘솔이 둘 다에게 알려 주므로 이
길로 오지 않는다. 여기서 막는 것은 **강제 종료**다 - 작업 관리자와,
시험/묶기 스크립트의 timeout.

무엇을 지키는가
---------------
    1. 묶이지 않았으면 지킴이를 띄우지 않는다   ★ 가장 중요
    2. 부모를 못 찾으면 조용히 넘어간다
    3. Job 은 자손을 데려간다(대조군 포함)
    4. uvicorn.run 을 그대로 쓴다

1번이 가장 중요하다. 개발 중에는 부모가 셸이나 pytest 이고, 그것이
끝날 때 os._exit 을 부르면 시험 자체를 끝내 버린다.

4번도 경계다. 시험 여섯 자리가 uvicorn.run 을 patch 해서 실제 서버가
뜨지 않게 막고 있다 - uvicorn.Server 로 바꾸면 회귀가 서버를 켠다.
"""

import io
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import launcher

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TheWatcherKnowsWhereItIsTest(unittest.TestCase):

    def test_묶이지_않았으면_지킴이를_띄우지_않는다(self):
        """
        이것이 뚫리면 pytest 가 끝날 때 os._exit 이 불린다 - 회귀가
        스스로를 끝낸다.
        """

        self.assertFalse(getattr(sys, "frozen", False),
                         "이 시험은 묶이지 않은 자리에서 돈다")

        self.assertEqual(launcher.watch_parent(), 0)

    def test_묶였다고_속여도_부모가_없으면_넘어간다(self):
        """부모를 못 찾는 자리에서도 켜지기는 해야 한다."""

        real_frozen = getattr(sys, "frozen", False)
        real_parent = launcher.parent_pid

        sys.frozen = True
        launcher.parent_pid = lambda: 0

        try:
            self.assertEqual(launcher.watch_parent(), 0)
        finally:
            launcher.parent_pid = real_parent

            if real_frozen:
                sys.frozen = real_frozen
            else:
                del sys.frozen

    def test_부모_번호를_구한다(self):
        """
        나를 띄운 것이 있다. 0 이면 지킴이가 아무 일도 하지 않으므로,
        번호를 구하는 것 자체가 보호의 전제다.
        """

        pid = launcher.parent_pid()

        self.assertIsInstance(pid, int)
        self.assertGreater(pid, 0)
        self.assertNotEqual(pid, os.getpid(), "자기 자신을 부모로 보았다")


class TheServerStartStaysPatchableTest(unittest.TestCase):
    """
    uvicorn.run 을 그대로 쓴다.

    이 저장소의 시험 여섯 자리가 uvicorn.run 을 patch 한다. 그것을
    uvicorn.Server 로 바꾸면 그 patch 가 빗나가고, 회귀가 실제 서버를
    켜기 시작한다 - 그때부터 회귀는 포트를 잡고 answers 를 기다린다.
    """

    def test_launcher_는_uvicorn_run_으로_켠다(self):
        source = open(os.path.join(HERE, "launcher.py"),
                      encoding="utf-8").read()

        self.assertIn("uvicorn.run(app", source)

    def test_지킴이는_signal_로_먼저_부탁한다(self):
        """
        곱게 끝내는 길을 먼저 시도한다. 곧바로 os._exit 을 부르면
        uvicorn 이 정리할 기회가 없다.
        """

        source = open(os.path.join(HERE, "launcher.py"),
                      encoding="utf-8").read()

        at = source.index("def _leave_when_parent_goes")
        body = source[at:at + 2200]

        self.assertIn("raise_signal", body)
        self.assertIn("os._exit", body)
        self.assertLess(body.index("raise_signal"), body.index("os._exit"),
                        "곱게 끝내기를 먼저 시도해야 한다")


class TheJobTakesTheChildrenTest(unittest.TestCase):
    """
    Job 을 걸었을 때만 자손이 함께 정리되는가.

    대조군을 함께 돌린다 - Job 없이 죽였을 때 ffmpeg 가 정말로 살아
    남는지 보여야, 걸었을 때 죽는 것이 Job 덕분이라고 말할 수 있다.
    """

    FFMPEG = os.path.join(HERE, "dist", "AI영상제작소", "tools", "ffmpeg.exe")

    # -re 가 없으면 ffmpeg 가 600초 분량을 최고속으로 몇 초 만에 끝낸다.
    # 그러면 "함께 죽었다"와 "제 할 일을 마쳤다"를 구별할 수 없다.
    WORK = ["-re", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
            "-t", "600", "-f", "null", "-"]

    def setUp(self):
        if not sys.platform.startswith("win"):
            self.skipTest("Windows 에서만 잴 수 있다")

        if not os.path.exists(self.FFMPEG):
            self.skipTest(f"ffmpeg 가 없다: {self.FFMPEG}")

    def _run(self, mode: str):
        """자식 프로세스에서 Job 을 걸거나 걸지 않고 ffmpeg 를 띄운다."""

        code = (
            "import os, subprocess, sys, time\n"
            "sys.path.insert(0, %r)\n"
            "import launcher\n"
            "if %r == 'on':\n"
            "    print('JOB=%%s' %% launcher.own_children(), flush=True)\n"
            "proc = subprocess.Popen([%r] + %r,\n"
            "    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "print('PID=%%d' %% proc.pid, flush=True)\n"
            "time.sleep(1.5)\n"
            "os._exit(0)\n"
        ) % (HERE, mode, self.FFMPEG, self.WORK)

        done = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", code],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)

        pid = None

        for line in (done.stdout or "").splitlines():
            if line.startswith("PID="):
                pid = int(line.split("=", 1)[1])

        return pid

    @staticmethod
    def _alive(pid: int) -> bool:
        import ctypes

        k = ctypes.windll.kernel32
        handle = k.OpenProcess(0x1000, False, pid)

        if not handle:
            return False

        try:
            code = ctypes.c_ulong()
            k.GetExitCodeProcess(handle, ctypes.byref(code))

            return code.value == 259
        finally:
            k.CloseHandle(handle)

    @staticmethod
    def _kill(pid: int) -> None:
        import ctypes

        k = ctypes.windll.kernel32
        handle = k.OpenProcess(0x0001, False, pid)

        if handle:
            k.TerminateProcess(handle, 0)
            k.CloseHandle(handle)

    def test_job_이_있을_때만_자손이_함께_간다(self):
        import time

        control = self._run("off")
        self.assertIsNotNone(control, "대조군 ffmpeg 를 띄우지 못했다")

        treated = self._run("on")
        self.assertIsNotNone(treated, "시험군 ffmpeg 를 띄우지 못했다")

        time.sleep(2.0)

        control_alive = self._alive(control)
        treated_alive = self._alive(treated)

        # 시험이 쓰레기를 남기지 않는다.
        for pid in (control, treated):
            if self._alive(pid):
                self._kill(pid)

        self.assertTrue(control_alive,
                        "대조군에서도 죽었다 - 이 시험은 Job 의 효과를 "
                        "가리지 못한다")
        self.assertFalse(treated_alive,
                         "Job 을 걸었는데도 ffmpeg 가 남았다")


if __name__ == "__main__":
    unittest.main()
