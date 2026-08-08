"""
Sprint171 - 받은 사람의 PC에서 정말 도는가 (Epic 58, Phase 3).

앞의 두 스프린트는 만드는 쪽에서 봤다. 여기서는 받는 쪽에서 본다 -
만든 exe를 실제로 켜서 영상이 나올 때까지 간다.

무엇을 흉내 내고 무엇을 못 하는가
---------------------------------
흉내 내는 것

    개발 환경 아닌 자리    저장소가 아닌 새 폴더에 복사해 놓고 부른다
    Python 없는 PC         PATH를 System32만 남기고, PYTHONHOME과
                           PYTHONPATH를 없는 자리로 가리킨다
    개발 도구 없는 PC      환경변수를 열 남짓만 넘긴다

못 하는 것

    진짜 새 PC             이 머신 하나뿐이다. Windows 자체에 들어
                           있는 것은 비울 수 없다.

그래서 이 파일이 증명하는 것은 "밖의 Python·개발 도구·PATH에 기대지
않는다"까지다. 그 너머는 다른 PC에서 켜 봐야 안다 - 그 사실을 숨기지
않는다.

묶은 것이 없으면 건너뛴다
-------------------------
여기서 묶지 않는다 - 몇 분이 걸리고, 만드는 일과 검사하는 일은 다르다.
dist에 배포 폴더가 있으면 그것을 본다.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app_info, error_log, runtime_paths
from app.services import media_tools

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RELEASE = os.path.join(REPO, "dist", app_info.NAME)
EXE_NAME = app_info.NAME + ".exe"
EXE = os.path.join(RELEASE, EXE_NAME)

HOST = "127.0.0.1"

# 받은 폴더에 있어야 하는 것들. release.SHAPE가 정한 그대로다.
EXPECTED = (EXE_NAME, media_tools.BESIDE_DIRNAME, "assets", "README.txt")


def _built() -> bool:
    return os.path.isfile(EXE)


def _skip_unless_built(test):
    if not _built():
        test.skipTest(f"묶은 것이 없다: {RELEASE}")


def clean_env(home, **extra):
    """
    받은 사람의 PC를 흉내 낸 환경.

    PATH를 비우는 것이 핵심이다 - 개발 PC에는 ffmpeg도 python도
    깔려 있어서, 그대로 두면 무엇에 기대고 있는지 알 수 없다.
    """

    env = {
        key: value for key, value in os.environ.items()
        if key.upper() in ("SYSTEMROOT", "TEMP", "TMP", "APPDATA",
                           "LOCALAPPDATA", "USERPROFILE", "COMSPEC",
                           "PATHEXT", "NUMBER_OF_PROCESSORS", "OS", "WINDIR")
    }

    env["AI_STUDIO_HOME"] = home
    env["PATH"] = os.path.join(env.get("SYSTEMROOT", r"C:\Windows"),
                               "System32")

    # 밖의 Python에 기대면 여기서 걸린다.
    env["PYTHONHOME"] = r"C:\없는곳\python"
    env["PYTHONPATH"] = r"C:\없는곳\lib"

    env.update(extra)

    return env


class Running:
    """켠 프로그램. 나갈 때 반드시 끈다."""

    def __init__(self, program, home, args=(), **extra):
        self.proc = subprocess.Popen(
            [program, "--no-browser", *args],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=clean_env(home, **extra), text=True, encoding="cp949",
            errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        self.lines = []
        self.url = None

        deadline = time.time() + 180

        while time.time() < deadline:
            line = self.proc.stdout.readline()

            if not line:
                if self.proc.poll() is not None:
                    break
                continue

            self.lines.append(line.rstrip())

            found = re.search(r"(http://127\.0\.0\.1:\d+/studio)", line)

            if found:
                self.url = found.group(1)
                break

    @property
    def said(self) -> str:
        return "\n".join(self.lines)

    def rest(self, seconds=2.0) -> str:
        """켜진 뒤에 더 찍은 것 - 알림은 주소 뒤에 온다."""

        import threading

        def read():
            while True:
                line = self.proc.stdout.readline()

                if not line:
                    break

                self.lines.append(line.rstrip())

        threading.Thread(target=read, daemon=True).start()
        time.sleep(seconds)

        return self.said

    def page(self, tries=90):
        for _ in range(tries):
            try:
                with urllib.request.urlopen(self.url, timeout=2) as answer:
                    return answer.read().decode("utf-8", "replace")
            except Exception:
                time.sleep(0.5)

        return None

    def call(self, path, body=None, method="GET", timeout=600):
        request = urllib.request.Request(
            self.url + path, method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={} if body is None
            else {"Content-Type": "application/json"})

        try:
            with urllib.request.urlopen(request, timeout=timeout) as answer:
                return json.loads(answer.read().decode("utf-8"))
        except urllib.error.HTTPError as failed:
            return {"__error__": failed.code,
                    "__detail__": failed.read().decode("utf-8", "replace")}

    def stop(self):
        import signal

        try:
            self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            self.proc.wait(timeout=25)
            return self.proc.returncode
        except Exception:
            pass

        self.proc.terminate()

        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)

        return self.proc.returncode

    def wait(self, timeout=180):
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()

        self.rest(0.5)

        return self.proc.returncode


class DeploymentTest(unittest.TestCase):
    """묶은 것을 실제로 켜는 검사들."""

    def setUp(self):
        _skip_unless_built(self)

        self.work = tempfile.mkdtemp(prefix="배포검사_")
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

        self.home = os.path.join(self.work, "유저")

    def _copy_release(self, name="푼것", without=()):
        """
        받은 폴더를 새 자리에 놓는다. 빼고 싶은 것을 뺄 수 있다.

        저장소의 dist를 그대로 쓰지 않는다 - 개발 자리 옆에서 도는
        것과 남의 폴더에서 도는 것은 다르다.
        """

        into = os.path.join(self.work, name)

        shutil.copytree(RELEASE, into)

        for relative in without:
            path = os.path.join(into, relative)

            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.remove(path)

        return into

    # ── 1. Clean PC 실행 ────────────────────────────────────────
    def test_clean_windows_boot(self):
        """
        푼 폴더를 그대로 켜면 Studio가 뜬다.

        압축을 풀고 두 번 누르는 것 말고 아무것도 하지 않는다.
        """

        folder = self._copy_release()

        running = Running(os.path.join(folder, EXE_NAME), self.home)
        self.addCleanup(running.stop)

        self.assertIsNotNone(running.url, f"주소를 못 찍었다: {running.said}")

        page = running.page()

        self.assertIsNotNone(page, "화면을 못 받았다")

        # 빈 화면이 아니라 쓰는 화면이다.
        for mark in ("무료 제작 시작", "내 자료 폴더 선택", "제작 준비"):
            with self.subTest(mark=mark):
                self.assertIn(mark, page)

        # 첫 실행 문구가 무엇을 켰는지 말한다.
        self.assertIn(app_info.NAME, running.said)
        self.assertIn(app_info.VERSION, running.said)

    def test_no_python_dependency(self):
        """
        밖의 Python에 기대지 않는다.

        PATH에 python이 없고, PYTHONHOME과 PYTHONPATH가 없는 자리를
        가리켜도 켜진다. 기대고 있었다면 여기서 죽는다.
        """

        env = clean_env(self.home)

        self.assertIsNone(shutil.which("python", path=env["PATH"]))
        self.assertFalse(os.path.exists(env["PYTHONHOME"]))

        running = Running(EXE, self.home)
        self.addCleanup(running.stop)

        self.assertIsNotNone(running.url, f"켜지지 않았다: {running.said}")
        self.assertIsNotNone(running.page())

    # ── 3. 데이터 보호 ──────────────────────────────────────────
    def test_user_data_isolated(self):
        """
        사람의 것은 사람의 자리에만 쌓인다.

        프로그램 폴더에 쌓이면 새 판을 덮어씌울 때 함께 사라진다.
        """

        folder = self._copy_release()
        before = sorted(os.listdir(folder))

        running = Running(os.path.join(folder, EXE_NAME), self.home)
        self.addCleanup(running.stop)

        self.assertIsNotNone(running.page())

        for name in ("output", ".workflow", ".dataset"):
            with self.subTest(name=name):
                self.assertTrue(
                    os.path.isdir(os.path.join(self.home, name)))

        self.assertEqual(sorted(os.listdir(folder)), before,
                         "프로그램 폴더에 무엇이 생겼다")
        self.assertEqual(sorted(before), sorted(EXPECTED))

        # 저장소에도 안 생긴다.
        self.assertFalse(os.path.exists(
            os.path.join(REPO, "output", os.path.basename(self.home))))

    def test_logs_appear_in_the_user_area_when_it_cannot_start(self):
        """켜지지 못했을 때의 기록도 사람의 자리에 남는다."""

        os.makedirs(self.home)

        # output 자리를 파일이 막고 있다 - 만들려다 실패한다.
        open(os.path.join(self.home, "output"), "w").close()

        running = Running(EXE, self.home)
        code = running.wait()

        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", running.said)
        self.assertIn("프로그램을 켜지 못했습니다", running.said)

        logs = os.path.join(self.home, error_log.DIRNAME)

        self.assertTrue(os.path.isdir(logs))
        self.assertEqual(len(os.listdir(logs)), 1)

    # ── 2. 무료 제작 전체 흐름 ──────────────────────────────────
    def test_full_free_mode_from_exe(self):
        """
        푼 폴더에서 대본을 넣고 영상이 나오기까지.

        API 키를 하나도 주지 않는다 - 무료 모드가 정말 아무것도 부르지
        않는다면 그래도 끝까지 간다.
        """

        folder = self._copy_release()
        ffmpeg = os.path.join(folder, media_tools.BESIDE_DIRNAME, "ffmpeg.exe")

        self.assertTrue(os.path.isfile(ffmpeg), "함께 온 ffmpeg가 없다")

        workspace = os.path.join(self.work, "내자료")

        for kind in ("images", "voices"):
            os.makedirs(os.path.join(workspace, kind))

        # 장면마다 다른 낱말이 걸리게 이름을 짓는다 - 같은 낱말을
        # 나눠 쓰면 한 파일이 두 장면에 걸려 검토가 된다.
        for name, colour in (("무릎 스트레칭", "red"), ("허리 세우기", "blue")):
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi",
                 "-i", f"color=c={colour}:s=1080x1920:d=1", "-frames:v", "1",
                 os.path.join(workspace, "images", f"{name}.png")],
                capture_output=True, check=True)

        for number, seconds in ((1, 2.4), (2, 2.1)):
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=f=330:d={seconds}",
                 "-ar", "24000", "-ac", "1",
                 os.path.join(workspace, "voices", f"scene{number}.wav")],
                capture_output=True, check=True)

        script = {
            "title": "아침 스트레칭 두 가지",
            "hook": "일어나서 2분이면 됩니다",
            "script": "무릎을 펴고 숨을 고릅니다. 그다음 허리를 세웁니다.",
            "scenes": [
                {"scene": 1, "narration": "무릎을 천천히 펴 주세요.",
                 "image_prompt": "무릎 스트레칭"},
                {"scene": 2, "narration": "이제 허리를 곧게 세웁니다.",
                 "image_prompt": "허리 세우기"},
            ],
        }

        running = Running(os.path.join(folder, EXE_NAME), self.home)
        self.addCleanup(running.stop)

        self.assertIsNotNone(running.page())

        # 배경 음악이 이 묶음에 있는가. 켤 때 프로그램이 스스로 말한다.
        #
        # 없으면 렌더는 마지막 단계에서 죽는다 - 그것을 여기서 실패로
        # 적으면 "묶기가 깨졌다"로 읽히지만, 실제로는 무엇을 함께 보낼지
        # 아직 정해지지 않은 것이다(저장소의 것은 2.9GB의 남의 트랙이다).
        if "배경 음악이 없어" in running.rest(1.5):
            self.skipTest(
                "이 묶음에는 배경 음악이 없다 - 렌더까지 보려면 "
                "PACKAGING_BGM 으로 함께 묶어야 한다")

        chosen = running.call("/api/workspace", {"root": workspace}, "PUT")

        self.assertEqual(chosen["counts"]["images"], 2)
        self.assertEqual(chosen["counts"]["voice"], 2)

        made = running.call(
            "/api/production/project",
            {"raw": json.dumps(script, ensure_ascii=False),
             "topic": script["title"], "channel": "wellbeing"}, "POST")

        project_id = made.get("project_id")

        self.assertIsNotNone(project_id, f"프로젝트를 못 만들었다: {made}")
        self.assertEqual(made["scene_count"], 2)

        running.call(
            f"/api/review/{project_id}/providers",
            {"providers": {"image": "local_stock", "voice": "local_voice"}},
            "PUT")

        scanned = running.call(
            f"/api/review/{project_id}/library", {}, "POST")

        self.assertEqual(scanned["counts"]["images"], 2)

        prepared = running.call(f"/api/review/{project_id}/preparation")

        self.assertEqual(prepared["state"], "ready",
                         f"준비가 안 됐다: {prepared}")

        for step in ("images", "voices"):
            answer = running.call(
                f"/api/review/{project_id}/{step}", {}, "POST")

            self.assertNotIn("__error__", answer,
                             f"{step}에서 멈췄다: {answer}")

        job = running.call(f"/api/review/{project_id}/render", {}, "POST")

        self.assertNotIn("__error__", job, f"렌더를 못 걸었다: {job}")

        outcome = None
        deadline = time.time() + 1200

        while time.time() < deadline:
            state = running.call(f"/api/jobs/{job['job_id']}")

            if state.get("state") in ("done", "failed"):
                outcome = state
                break

            time.sleep(5)

        self.assertIsNotNone(outcome, "렌더가 끝나지 않았다")
        self.assertEqual(
            outcome.get("state"), "done",
            f"렌더가 실패했다: {json.dumps(outcome, ensure_ascii=False)[:800]}")

        check = running.call(f"/api/review/{project_id}/output-check")

        self.assertEqual(check["state"], "ready",
                         f"결과에 문제가 있다: {check.get('issues')}")
        self.assertTrue(check["video"]["exists"])
        self.assertGreater(check["video"]["seconds"] or 0, 0)

        # 만든 것은 사람의 자리에 있다.
        video = os.path.join(self.home, "output", project_id)

        self.assertTrue(os.path.isdir(video))

    # ── 4. 오류 상황 ────────────────────────────────────────────
    def test_missing_tools_error(self):
        """
        tools/가 없으면 사람이 읽을 수 있는 말로 세운다.

        exe만 떼어 낸 경우가 이것이다. moviepy는 들이는 순간 ffmpeg를
        찾고 없으면 RuntimeError를 던지므로, 그 앞에서 우리가 먼저
        말한다 - 라이브러리의 문장에는 무엇을 어디에 넣으라는 말이 없다.
        """

        alone = os.path.join(self.work, "떼어낸것")
        os.makedirs(alone)

        shutil.copyfile(EXE, os.path.join(alone, EXE_NAME))

        running = Running(os.path.join(alone, EXE_NAME), self.home)
        code = running.wait()

        said = running.said

        self.assertEqual(code, 1)
        self.assertIn("ffmpeg", said)
        self.assertIn(media_tools.BESIDE_DIRNAME, said)
        self.assertIn("통째로", said)

        # 라이브러리의 말이 아니라 우리 말이다.
        self.assertNotIn("Traceback", said)
        self.assertNotIn("IMAGEIO_FFMPEG_EXE", said)

    def test_a_taken_port_does_not_stop_it(self):
        """이미 쓰이는 자리를 골라도 켜진다."""

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
            taken.bind((HOST, 0))
            taken.listen(1)

            busy = taken.getsockname()[1]

            running = Running(EXE, self.home, ["--port", str(busy)])
            self.addCleanup(running.stop)

            self.assertIsNotNone(running.url)
            self.assertNotIn(f":{busy}/", running.url)
            self.assertIn("이미 쓰이고 있어", running.said)
            self.assertIsNotNone(running.page())

    @unittest.expectedFailure
    def test_an_unreadable_workspace_is_reported_not_pretended(self):
        """
        읽을 수 없는 폴더를 고르면 그렇다고 말해야 한다.

        아직 그렇지 않다 - expectedFailure로 둔다
        -----------------------------------------
        고치는 것은 무료 모드를 건드리는 일이고, 이번 스프린트가 그것을
        금지했다. 지운 채로 두면 다음 사람이 이 결함을 모른다. 그래서
        "알고 있고 아직 안 고쳤다"로 남긴다 - 고치면 여기가 뜻밖의
        성공으로 뜨고, 그때 이 표시를 떼면 된다.

        Sprint171 실측에서 이것이 깨져 있었다 - C:\\Windows\\System32\\
        config 는 listdir이 PermissionError를 내는 폴더인데, 훑는 쪽이
        os.walk를 쓰면서 그 오류를 조용히 넘겨 "자료 0개"로 보고했다.

        고른 사람은 제 파일 이름이 잘못됐다고 생각하고 이름을 고치기
        시작한다. 실제로는 그 폴더를 읽을 수 없었을 뿐이다.

        무료 모드를 고치는 것은 이번 스프린트가 금지했으므로, 여기서는
        그 사실만 못으로 박아 둔다. 고치면 이 테스트가 초록이 된다.
        """

        blocked = r"C:\Windows\System32\config"

        if not os.path.isdir(blocked):
            self.skipTest("이 PC에는 그 폴더가 없다")

        try:
            os.listdir(blocked)
        except PermissionError:
            pass
        else:
            self.skipTest("이 계정은 그 폴더를 읽을 수 있다")

        running = Running(EXE, self.home)
        self.addCleanup(running.stop)

        self.assertIsNotNone(running.page())

        answer = running.call("/api/workspace", {"root": blocked}, "PUT")

        self.assertIn(
            "__error__", answer,
            "읽지 못한 폴더를 '자료 0개'로 받았다 - 되는 척이다. "
            f"받은 답: {answer}")

    # ── 5. 배포 체크 ────────────────────────────────────────────
    def test_readme_matches_bundle(self):
        """
        README가 말하는 것이 실제로 그 폴더에 있다.

        받은 사람이 처음 믿는 글이다. 여기가 틀리면 사람은 없는 폴더를
        찾아 헤맨다.
        """

        with open(os.path.join(RELEASE, "README.txt"), encoding="utf-8") as f:
            readme = f.read()

        # 이름·판번호는 프로그램이 말하는 것과 같아야 한다.
        self.assertIn(app_info.NAME, readme)
        self.assertIn(app_info.VERSION, readme)

        # 폴더 이야기는 실제 폴더와 맞아야 한다.
        for name in EXPECTED:
            with self.subTest(name=name):
                self.assertTrue(os.path.exists(os.path.join(RELEASE, name)),
                                f"README가 말하는 {name}이 없다")

        for mentioned in (EXE_NAME, media_tools.BESIDE_DIRNAME, "assets"):
            with self.subTest(mentioned=mentioned):
                self.assertIn(mentioned, readme)

        # 내 것이 어디 쌓이는지, 안 켜질 때 어디를 보는지.
        self.assertIn(runtime_paths.APP_DIRNAME, readme)
        self.assertIn(error_log.DIRNAME, readme)

        # 판번호를 두 자리에 손으로 적지 않는다.
        self.assertEqual(readme.count(app_info.VERSION), 1)


if __name__ == "__main__":
    unittest.main()
