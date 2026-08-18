"""
Sprint220 - Desktop Host 프로토타입의 구조를 못 박는다.

여기서 재지 않는 것
-------------------
창이 실제로 뜨는가, 대화상자가 뜨는가는 재지 않는다. 그것은 GUI 가
있는 자리에서만 잴 수 있고, 이 파일은 창이 없는 자리에서도 돌아야
한다(pytest 는 그런 자리에서도 불린다).

창에 관한 검증은 tests/smoke_host_desktop.py 가 맡는다 - 이름이
test_ 로 시작하지 않으므로 pytest 가 집어가지 않는다. 일부러 그렇게
두었다.

여기서 재는 것
--------------
    1. pywebview 없이도 이 모듈을 들일 수 있는가   ★ 가장 중요
    2. 127.0.0.1 밖으로 나가지 않는가
    3. 포트 고르기와 --port 읽기
    4. 창에 띄우는 안내가 바깥을 부르지 않는가
    5. 서버가 뜨고 멈추는가

1번이 중요한 이유는, 이 저장소가 pywebview 를 의존으로 갖지 않기
때문이다. 모듈 최상단에서 import webview 를 하면 그 순간 이 파일도
기존 regression 도 전부 실패한다.
"""

import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import host_desktop


def test_모듈은_pywebview_없이도_들어온다():
    """최상단에서 webview 를 들이지 않는다."""

    source = open(host_desktop.__file__, encoding="utf-8").read()

    for line in source.splitlines():
        # 들여쓴 줄은 함수 안이다 - 거기서 늦게 들이는 것은 괜찮다.
        # 우리가 막는 것은 모듈이 들어오는 순간 함께 딸려오는 것뿐이다.
        if line[:1] in (" ", "\t"):
            continue

        assert not line.startswith(("import webview", "from webview")), \
            "webview 를 최상단에서 들이면 pywebview 없는 자리가 전부 깨진다"


def test_주소는_루프백_밖으로_나가지_않는다():
    assert host_desktop.HOST == "127.0.0.1"

    url = host_desktop.studio_url(12345)

    assert url == "http://127.0.0.1:12345/studio"
    assert "0.0.0.0" not in url
    assert "localhost" not in url


def test_고른_포트는_실제로_비어_있다():
    port = host_desktop.choose_port()

    assert isinstance(port, int)
    assert 1 <= port <= 65535

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host_desktop.HOST, port))


def test_차지된_자리를_달라고_하면_다른_자리로_간다():
    """멈추지 않는다 - 멈춰 봐야 사람이 할 수 있는 일이 없다."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind((host_desktop.HOST, 0))
        taken.listen(1)

        busy = taken.getsockname()[1]

        assert host_desktop.choose_port(busy) != busy


@pytest.mark.parametrize("argv,expected", [
    ([], None),
    (["--port"], None),
    (["--port", "8080"], 8080),
    (["--port", "이건숫자가아니다"], None),
    (["--check", "--port", "9999"], 9999),
])
def test_port_읽기(argv, expected):
    assert host_desktop.asked_port(argv) == expected


def test_창에_띄우는_안내는_바깥을_부르지_않는다():
    """
    켜지 못한 화면이 인터넷을 필요로 하면, 인터넷이 없어서 못 켠
    사람에게 그 화면은 비어 있다.
    """

    pages = [host_desktop.SPLASH,
             host_desktop.failure_page("이유", "자세한 것")]

    for page in pages:
        assert "http://" not in page
        assert "https://" not in page


def test_실패_화면은_이유를_그대로_담는다():
    page = host_desktop.failure_page("ffmpeg 가 없습니다", "tools 폴더")

    assert "ffmpeg 가 없습니다" in page
    assert "tools 폴더" in page


def test_서버가_뜨고_멈춘다():
    """
    창 없이 서버만. 이 하나가 Desktop Host 의 뼈대다 - 메인 스레드를
    비워 두고 서버를 옆으로 옮길 수 있는가.
    """

    port = host_desktop.choose_port()
    server = host_desktop.ServerThread(port)

    server.start()

    try:
        assert host_desktop.wait_until_serving(port, timeout=90.0), \
            f"서버가 {port} 에서 응답하지 않는다"
        assert server.alive()
    finally:
        stopped = server.stop()

    assert stopped, "창이 닫혔는데 서버 스레드가 남아 있다"
    assert not server.alive()


# --- Sprint221 - 수명 ---------------------------------------------------


def test_shutdown_은_서버가_없어도_견딘다():
    """창이 뜨기 전에 닫히는 길이 있다. 거기서 터지면 안 된다."""

    assert host_desktop.shutdown(None) is True


def test_running_jobs_는_목록을_돌려주고_던지지_않는다():
    """
    이 함수가 예외를 던지면 창이 닫히지 않는다 - 사람이 프로그램에
    갇힌다. 무슨 일이 있어도 목록이어야 한다.
    """

    jobs = host_desktop.running_jobs()

    assert isinstance(jobs, list)
    assert all(job.get("state") == "running" for job in jobs)


def test_running_jobs_는_studio_jobs_가_없어도_빈_목록(monkeypatch):
    import builtins

    real = builtins.__import__

    def boom(name, *args, **kwargs):
        if name == "app.services" or name.startswith("app.services.studio"):
            raise ImportError("없는 셈 치자")

        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", boom)

    assert host_desktop.running_jobs() == []


def test_무엇이_도는지_이름을_댄다():
    """숫자만 보여 주면 사람은 무엇을 잃는지 모른 채 누른다."""

    said = host_desktop._describe([
        {"kind": "generate", "title": "무릎 스트레칭"},
        {"kind": "upload", "title": ""},
    ])

    assert "영상 만들기" in said
    assert "무릎 스트레칭" in said
    assert "업로드" in said


def test_도는_것이_많으면_줄여서_말한다():
    jobs = [{"kind": "generate", "title": f"{n}"} for n in range(9)]

    said = host_desktop._describe(jobs)

    assert said.count("·") == 6  # 다섯 줄 + "그 밖에" 한 줄
    assert "그 밖에 4개" in said


def test_자식_수명_규칙은_별도_프로세스에서_건다():
    """
    own_children() 은 이 프로세스를 Job 에 넣는다. 그것을 pytest 안에서
    부르면 테스트 러너 전체가 그 Job 에 들어가므로, 따로 띄운 프로세스
    에서 확인한다.

    두 번 불러도 같은 답이어야 한다 - 창이 다시 열릴 때마다 Job 을
    새로 만들면 핸들이 쌓인다.
    """

    import subprocess

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import host_desktop\n"
        "first = host_desktop.own_children()\n"
        "second = host_desktop.own_children()\n"
        "print(first, second, host_desktop._job is not None)\n"
    ) % here

    # encoding 을 말하지 않으면 콘솔 코드페이지로 읽혀 한글이 깨진다.
    # 이 저장소는 그것을 test_subprocess_encoding 이 지키고 있다.
    done = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)

    said = (done.stdout or "").strip().split()

    assert len(said) == 3, f"예상 밖 출력: {done.stdout!r} {done.stderr[-300:]!r}"

    first, second, held = said

    assert first == second, "같은 프로세스에서 답이 달라졌다"

    if first == "True":
        assert held == "True", "성공했다면서 Job 핸들을 놓았다"
