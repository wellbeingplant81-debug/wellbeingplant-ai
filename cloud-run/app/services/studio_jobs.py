"""
Sprint80 - UI에서 생성을 돌리고 진행을 보여 주기 위한 작업 관리.

파이프라인은 한 줄도 바꾸지 않는다. 여기서 하는 것은 두 가지다.

  1. 생성을 스레드에서 돌린다 - HTTP 요청 하나가 10분을 붙잡고 있으면
     브라우저가 먼저 끊는다.
  2. 돌아가는 동안의 stdout을 모은다 - Console 패널이 보여 줄 것이
     그것이고, 파이프라인은 이미 충분히 많은 것을 print한다.

진행 단계는 여기서 판정하지 않는다. studio_service.stage_progress가
디스크의 산출물로 판정한다 - 로그 문구에 기대면 파이프라인이 print를
바꿀 때마다 UI가 조용히 틀린다.
"""

import io
import threading
import traceback
import uuid


# Console에 남길 줄 수. 무한히 쌓으면 긴 생성에서 메모리가 계속 는다.
MAX_CONSOLE_LINES = 400


_lock = threading.Lock()
_jobs = {}


class _Tee(io.TextIOBase):
    """원래 stdout으로도 흘리고, 작업 버퍼에도 쌓는다.

    가로채기만 하면 터미널에서 생성 과정을 볼 수 없게 된다. 관측이
    기존 동작을 없애지 않는다는 원칙은 여기에도 그대로 적용된다.
    """

    def __init__(self, original, job_id):
        self._original = original
        self._job_id = job_id
        self._partial = ""

    def write(self, text):
        try:
            self._original.write(text)
        except Exception:
            pass

        self._partial += text

        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            _append_line(self._job_id, line)

        return len(text)

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass


# factory_service가 프로젝트를 만든 직후 찍는 줄. 이것 하나로 생성
# 중에도 어느 디렉터리를 보면 되는지 알 수 있다.
#
# 진행 단계를 로그로 판정하지는 않는다 - 그건 여전히 디스크의 산출물이
# 정한다. 여기서 로그로 얻는 것은 "어디를 볼 것인가"뿐이고, 그것 없이는
# 생성이 끝날 때까지 진행률을 전혀 보여 줄 수 없다.
_PROJECT_LINE = "Project :"


def _append_line(job_id: str, line: str) -> None:
    line = line.rstrip()

    if not line:
        return

    with _lock:
        job = _jobs.get(job_id)

        if job is None:
            return

        if job["project_path"] is None and line.startswith(_PROJECT_LINE):
            job["project_path"] = line[len(_PROJECT_LINE):].strip()

        job["console"].append(line)

        if len(job["console"]) > MAX_CONSOLE_LINES:
            del job["console"][:-MAX_CONSOLE_LINES]


def _new_job(job_id, topic, channel, project_id=None, project_path=None):
    return {
        "job_id": job_id,
        "kind": "generate",
        "topic": topic,
        "channel": channel,
        "state": "running",
        "project_id": project_id,
        "project_path": project_path,
        "title": None,
        "error": None,
        "console": [],
    }


def start(topic: str, channel: str = "wellbeing") -> str:
    """생성을 시작하고 job_id를 돌려준다."""

    job_id = uuid.uuid4().hex[:12]

    with _lock:
        _jobs[job_id] = _new_job(job_id, topic, channel)

    thread = threading.Thread(
        target=_run, args=(job_id, topic, channel), daemon=True,
    )
    thread.start()

    return job_id


def start_regeneration(project_id: str, project_path: str,
                       scenes=None) -> str:
    """
    Sprint81 - 재생성을 같은 작업 틀로 돌린다.

    엔진을 부르는 것 말고는 생성 작업과 다를 것이 없다 - 몇 분이 걸리고,
    stdout에 결정 로그가 흐르고, 화면은 그 둘을 폴링한다. 틀을 따로
    만들면 콘솔 수집과 상태 전이를 두 번 구현하게 된다.
    """

    job_id = uuid.uuid4().hex[:12]

    with _lock:
        job = _new_job(job_id, None, None, project_id, project_path)
        job["kind"] = "regenerate"
        job["scenes"] = list(scenes) if scenes else None
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_regeneration, args=(job_id, project_path, scenes),
        daemon=True,
    )
    thread.start()

    return job_id


def _run_regeneration(job_id: str, project_path: str, scenes) -> None:
    import sys

    from app.services import studio_regeneration

    original = sys.stdout
    sys.stdout = _Tee(original, job_id)

    try:
        studio_regeneration.regenerate(project_path, scenes)

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "done"

    except Exception as exc:
        _append_line(job_id, f"[Studio] 재생성 실패: {exc}")
        _append_line(job_id, traceback.format_exc())

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "failed"
                job["error"] = str(exc)

    finally:
        sys.stdout = original


def _run(job_id: str, topic: str, channel: str) -> None:
    import sys

    # 늦은 import - 이 모듈을 읽는 것만으로 파이프라인 전체가 딸려
    # 오지 않게 한다(테스트가 가벼워진다).
    from app.services.factory_service import generate_short_video

    original = sys.stdout
    sys.stdout = _Tee(original, job_id)

    try:
        result = generate_short_video(topic=topic, channel=channel)

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "done"
                job["project_id"] = result.get("project_id")
                job["title"] = result.get("title")

    except Exception as exc:
        _append_line(job_id, f"[Studio] 생성 실패: {exc}")
        _append_line(job_id, traceback.format_exc())

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "failed"
                job["error"] = str(exc)

    finally:
        sys.stdout = original


def start_oauth(action: str) -> str:
    """
    Sprint90 - OAuth 동작을 백그라운드로 돌린다.

    OneDrive 원본은 이것을 OAuthWorker(QThread)로 했다. 그 클래스가 한
    일은 "콜러블 하나를 백그라운드에서 실행하고 끝나면 알린다"가 전부라,
    이미 있는 이 작업 틀이 그대로 대신한다 - 새 동시성 구조를 만들지
    않는다.

    백그라운드로 돌리는 이유도 원본과 같다. reauthenticate()는 브라우저
    리다이렉트를 기다리며 최장 수백 초 블로킹한다. 요청 스레드에서
    그대로 부르면 HTTP 응답이 그동안 돌아오지 않는다.
    """

    from app.services import oauth_manager as oauth_module

    job_id = uuid.uuid4().hex[:12]

    with _lock:
        job = _new_job(job_id, None, None)
        job["kind"] = "oauth"
        job["action"] = action
        job["health"] = None
        _jobs[job_id] = job

    def run():
        manager = oauth_module.build_default_oauth_manager()
        target = {
            "login": manager.reauthenticate,
            "refresh": manager.verify_now,
            "logout": manager.logout,
        }[action]
        return target()

    thread = threading.Thread(
        target=_run_oauth, args=(job_id, run), daemon=True,
    )
    thread.start()

    return job_id


def _run_oauth(job_id: str, target_fn) -> None:
    import sys

    original = sys.stdout
    sys.stdout = _Tee(original, job_id)

    try:
        health = target_fn()

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "done"
                job["health"] = {
                    "status": health.status,
                    "message": health.message,
                    "checked_at": health.checked_at,
                }

    except Exception as exc:
        _append_line(job_id, f"[Studio] OAuth 실패: {exc}")
        _append_line(job_id, traceback.format_exc())

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "failed"
                job["error"] = str(exc)

    finally:
        sys.stdout = original


def status(job_id: str, console_from: int = 0) -> dict:
    """
    작업 상태와 콘솔. console_from부터의 줄만 돌려준다 - 화면이 1초마다
    물어보는데 매번 전체를 보내면 긴 생성에서 응답이 계속 커진다.
    """

    with _lock:
        job = _jobs.get(job_id)

        if job is None:
            return {"found": False}

        console = job["console"]
        start_at = max(0, min(console_from, len(console)))

        return {
            "found": True,
            "job_id": job["job_id"],
            "kind": job.get("kind", "generate"),
            "state": job["state"],
            "topic": job["topic"],
            "channel": job["channel"],
            "project_id": job["project_id"],
            "project_path": job["project_path"],
            "title": job["title"],
            "error": job["error"],
            "health": job.get("health"),
            "console": list(console[start_at:]),
            "console_next": len(console),
        }


def recent(limit: int = 10) -> list:
    """최근 작업들. Dashboard가 쓴다."""

    with _lock:
        jobs = list(_jobs.values())

    return [
        {
            "job_id": job["job_id"],
            "state": job["state"],
            "topic": job["topic"],
            "project_id": job["project_id"],
            "title": job["title"],
        }
        for job in jobs[-limit:][::-1]
    ]


def reset() -> None:
    """테스트용. 작업 기록을 비운다."""

    with _lock:
        _jobs.clear()
