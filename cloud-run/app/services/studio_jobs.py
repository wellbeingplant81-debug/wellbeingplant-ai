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
import os
import re
import threading
import traceback
import uuid


# Sprint198 - 실패했을 때 화면에 뜨는 글에서 경로를 가린다.
#
# 예외를 던지는 자리는 Render Engine과 Provider라 건드리지 않는다.
# 대신 화면으로 나갈 때만 가린다 - 예외 객체는 원문을 그대로 들고
# 있으므로 로그와 터미널에서는 전체 경로를 볼 수 있다. 보는 사람이
# 다르면 보이는 것도 달라야 한다.
#
# 드라이브 문자로 시작해 구분자로 이어지는 조각들을 한 덩이로 본다.
# 조각 안에 공백이 있어도 된다 - 이 저장소의 경로에는 주제명이 들어가
# "무릎 통증 완화 스트레칭" 같은 폴더가 실제로 생긴다. \S+ 로 끊으면
# "무릎"까지만 지우고 나머지가 남는다.
#
# 따옴표·꺾쇠는 조각에 넣지 않는다. traceback의 File "..." 과 ffmpeg의
# '...' 이 그 문자로 끝나기 때문이다.
_A_PATH = re.compile(
    r"[A-Za-z]:[\\/](?:[^\\/\r\n\"'<>|*?:]*[\\/])*[^\\/\r\n\"'<>|*?:]*"
)

# 경로 뒤에 붙은 문장 부호. 파일 이름에 눌어붙지 않게 떼었다 붙인다.
_TRAILING = " \t.,;:)]}-"


def _places():
    """
    가릴 자리들. 긴 것부터 본다.

    짧은 것을 먼저 맞춰 보면 그 안에 든 긴 것이 영영 안 걸린다 -
    내 자료 폴더는 사용자 홈 아래에 있다.
    """

    from app import runtime_paths

    found = []

    for tag, get in (("<data_path>", runtime_paths.home),
                     ("<app_path>", runtime_paths.program_dir),
                     ("<app_path>", runtime_paths.bundle_root),
                     ("<user_path>", lambda: os.path.expanduser("~"))):
        try:
            where = get()
        except Exception:
            # 가리기가 실패의 길을 막으면 안 된다. 못 알아본 자리는
            # 아래 <path>가 받는다.
            continue

        if where:
            found.append((os.path.normpath(where).rstrip("\\/"), tag))

    return sorted(found, key=lambda pair: len(pair[0]), reverse=True)


def _tag_for(path: str, places) -> str:
    lowered = os.path.normpath(path).lower()

    for where, tag in places:
        if lowered.startswith(where.lower()):
            return tag

    return "<path>"


def _masked(text: str) -> str:
    """
    화면으로 나갈 글에서 절대 경로를 가린다. 파일 이름은 남긴다.

    어느 파일에서 났는지는 알 수 있어야 고칠 수 있다. 지우는 것은
    그 파일이 어디에 있는가뿐이다.
    """

    if not text:
        return ""

    places = _places()

    def swap(found):
        whole = found.group(0)
        tail = ""

        while whole and whole[-1] in _TRAILING:
            tail = whole[-1] + tail
            whole = whole[:-1]

        if not whole:
            return found.group(0)

        name = re.split(r"[\\/]", whole)[-1]
        tag = _tag_for(whole, places)

        return (f"{tag}\\{name}" if name else tag) + tail

    return _A_PATH.sub(swap, text)


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


def _started_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _new_job(job_id, topic, channel, project_id=None, project_path=None):
    return {
        "job_id": job_id,
        "kind": "generate",
        # Sprint149 - 언제 시작했나. 큐 화면이 "업로드 중"인 작업의
        # 시작 시각을 보여 준다.
        "started_at": _started_now(),
        "topic": topic,
        "channel": channel,
        "state": "running",
        "project_id": project_id,
        "project_path": project_path,
        "title": None,
        "error": None,
        "console": [],
    }


def start(topic: str, channel: str = "wellbeing",
          project_id: str = None) -> str:
    """생성을 시작하고 job_id를 돌려준다.

    Sprint107 - project_id를 주면 미리 만들어 둔 프로젝트로 만든다.
    주지 않으면 예전과 같다."""

    job_id = uuid.uuid4().hex[:12]

    with _lock:
        _jobs[job_id] = _new_job(job_id, topic, channel, project_id)

    thread = threading.Thread(
        target=_run, args=(job_id, topic, channel, project_id), daemon=True,
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
        _append_line(job_id, _masked(f"[Studio] 재생성 실패: {exc}"))
        _append_line(job_id, _masked(traceback.format_exc()))

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "failed"
                job["error"] = _masked(str(exc))

    finally:
        sys.stdout = original


def _project_path_of(result) -> str:
    """
    만든 것이 어디 있는가. 결과를 볼 때만 쓴다.

    엔진이 제 입으로 알려 준 자리를 쓴다. 여기서 project_id로 경로를
    다시 지으면 규칙이 두 벌이 되고, 그 둘은 언젠가 어긋난다 -
    실제로 한 번 어긋났다. project_service.OUTPUT_ROOT는 들일 때
    한 번 정해지는 값이라, 개발 중에는 작업 디렉터리 기준의 상대
    경로다. 그것으로 지은 자리는 만든 것이 있는 자리가 아니었다.
    """

    if not isinstance(result, dict):
        return None

    return result.get("output") or result.get("project_path")


def _run(job_id: str, topic: str, channel: str,
         project_id: str = None) -> None:
    import sys

    # 늦은 import - 이 모듈을 읽는 것만으로 파이프라인 전체가 딸려
    # 오지 않게 한다(테스트가 가벼워진다).
    from app.services.factory_service import generate_short_video

    # Sprint176 - 베타 사용 기록. 여기가 만들기의 가장 바깥 자리다.
    #
    # 예전에는 화면이 이 작업을 물어볼 때 결과를 적었다. 아무도
    # 물어보지 않으면 아무것도 안 적혔고, 창을 닫아 두고 기다린
    # 사람의 렌더는 기록에 없었다 - 우리가 알고 싶은 것이 정확히
    # 그 사람이다.
    #
    # 무엇을 적을지와 "됐다고 볼 수 있는가"는 beta_render_events가
    # 정한다. 여기서는 부르기만 한다 - 이 파일은 작업을 굴리는
    # 자리이지 판단하는 자리가 아니다.
    from app.services import beta_render_events

    original = sys.stdout
    sys.stdout = _Tee(original, job_id)

    beta_render_events.started()

    try:
        result = generate_short_video(
            topic=topic, channel=channel, project_id=project_id,
        )

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "done"
                job["project_id"] = result.get("project_id")
                job["title"] = result.get("title")

        beta_render_events.finished(_project_path_of(result))

    except Exception as exc:
        _append_line(job_id, _masked(f"[Studio] 생성 실패: {exc}"))
        _append_line(job_id, _masked(traceback.format_exc()))

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "failed"
                job["error"] = _masked(str(exc))

        beta_render_events.crashed(exc)

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


def start_social(platform: str, action: str) -> str:
    """
    Sprint217 - SNS 로그인/로그아웃/확인을 백그라운드로 돌린다.

    백그라운드로 돌리는 이유는 start_oauth와 같다 - 로그인은 브라우저
    리다이렉트를 최장 300초 기다리며 블로킹한다. 요청 스레드에서 그대로
    부르면 그동안 HTTP 응답이 돌아오지 않고, 화면은 얼어 있는 것처럼
    보인다.

    start_oauth와 합치지 않는다. 저쪽은 health 하나를 돌려주고 이쪽은
    계정 한 덩이(연결 여부·계정 이름·무엇이 없는가)를 돌려준다 -
    돌려주는 것이 다른 두 일을 한 함수에 넣으면 어느 쪽 모양인지
    부르는 곳에서 알 수 없게 된다.
    """

    from app.services import social_accounts as social_module

    job_id = uuid.uuid4().hex[:12]

    with _lock:
        job = _new_job(job_id, None, None)
        job["kind"] = "social"
        job["platform"] = platform
        job["action"] = action
        job["account"] = None
        _jobs[job_id] = job

    def run():
        manager = social_module.build_default_social_auth_manager()
        provider = manager.provider(platform)

        return {
            "login": provider.login,
            "logout": provider.logout,
            "refresh": provider.refresh_token,
        }[action]()

    thread = threading.Thread(
        target=_run_social, args=(job_id, run), daemon=True,
    )
    thread.start()

    return job_id


def _run_social(job_id: str, target_fn) -> None:
    """
    Sprint217 - 실패를 조용히 삼키지 않는다.

    _run_oauth는 예외를 job["error"]에 담았지만 화면이 그것을 읽지
    않아서, 사람에게는 "눌러도 아무 반응 없음"이 됐다. 여기서는
    실패해도 account 한 덩이를 반드시 채운다 - 화면이 그릴 것이 늘
    있어야 한다. traceback은 콘솔에 남긴다.
    """

    import sys

    from app.services import social_accounts as social_module

    original = sys.stdout
    sys.stdout = _Tee(original, job_id)

    try:
        account = target_fn()

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "done"
                job["account"] = account.as_dict()

    except Exception as exc:
        _append_line(job_id, _masked(f"[Studio] SNS 처리 실패: {exc}"))
        _append_line(job_id, _masked(traceback.format_exc()))

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "failed"
                job["error"] = _masked(str(exc))
                # 화면이 그릴 것을 여기서도 만들어 준다. 상태는
                # UNKNOWN이다 - 연결됐다고 말하지 않는다.
                job["account"] = social_module.SocialAccount(
                    job.get("platform", ""), social_module.UNKNOWN,
                    _masked(str(exc)),
                ).as_dict()

    finally:
        sys.stdout = original


def start_upload(project_id: str, project_path: str) -> str:
    """
    Sprint92 - 승인된 프로젝트를 올린다.

    백그라운드로 돌리는 이유는 생성/재생성과 같다 - 실제 업로드는
    영상 파일을 통째로 전송하므로 요청 스레드에서 부르면 그동안 HTTP
    응답이 돌아오지 않는다.
    """

    from app.services import studio_upload

    job_id = uuid.uuid4().hex[:12]

    with _lock:
        job = _new_job(job_id, None, None, project_id, project_path)
        job["kind"] = "upload"
        job["upload"] = None
        _jobs[job_id] = job

    def run():
        return studio_upload.run_upload(
            project_path, studio_upload.default_store_path(),
        )

    thread = threading.Thread(
        target=_run_upload, args=(job_id, run), daemon=True,
    )
    thread.start()

    return job_id


def _run_upload(job_id: str, target_fn) -> None:
    import sys

    original = sys.stdout
    sys.stdout = _Tee(original, job_id)

    try:
        result = target_fn()

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                # 업로드가 거절되거나 실패해도 작업 자체는 끝난 것이다 -
                # 무슨 일이 있었는지는 upload가 그대로 담는다.
                job["state"] = "done"
                job["upload"] = result

    except Exception as exc:
        _append_line(job_id, _masked(f"[Studio] 업로드 실패: {exc}"))
        _append_line(job_id, _masked(traceback.format_exc()))

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "failed"
                job["error"] = _masked(str(exc))

    finally:
        sys.stdout = original


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
        _append_line(job_id, _masked(f"[Studio] OAuth 실패: {exc}"))
        _append_line(job_id, _masked(traceback.format_exc()))

        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["state"] = "failed"
                job["error"] = _masked(str(exc))

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
            "upload": job.get("upload"),
            # Sprint217 - SNS 계정 한 덩이. 실패해도 채워져 있다.
            "platform": job.get("platform"),
            "account": job.get("account"),
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
            # Sprint148 - 무슨 작업인가. 업로드 중인 프로젝트를
            # 생성 중으로 읽지 않으려면 종류를 알아야 한다.
            "kind": job.get("kind", "generate"),
            # Sprint149 - 언제 시작했나. 작업이 곧 실행이므로 작업이
            # 안다. 끝난 시각은 산출물이 말한다.
            "started_at": job.get("started_at"),
        }
        for job in jobs[-limit:][::-1]
    ]


def reset() -> None:
    """테스트용. 작업 기록을 비운다."""

    with _lock:
        _jobs.clear()
