"""
Sprint217 - 자격증명이 어디 있는가 (Epic 61).

이 파일이 고치는 실제 결함
--------------------------
바탕화면의 AI영상제작소.exe에서 [Google 로그인]을 누르면 브라우저가
열리지 않았다. 원인은 다음 한 줄이었다(oauth_manager.py).

    os.environ.get("YOUTUBE_OAUTH_CLIENT_SECRET_PATH",
                   "credentials/client_secret.json")

**상대 경로다.** 개발 중에는 cloud-run/ 에서 켜므로 맞는다. 그런데
묶은 프로그램은 사람이 두 번 누른 자리에서 켜지고, 그 자리는 바탕화면
이다 - 거기에 credentials/ 는 없다. 실측한 응답은 이랬다.

    POST /studio/api/oauth/login
    -> health.status = UNKNOWN
       "Google OAuth authentication failed for account default:
        [Errno 2] No such file or directory: 'credentials/client_secret.json'"

브라우저는 열릴 기회가 없었다. InstalledAppFlow가 client_secret 파일을
읽는 것이 첫 걸음이고 거기서 죽었다.

어디로 옮기는가
---------------
사용자 자리 아래로 간다 - output/ · .workflow/ · music/ 이 이미 사는
그 자리다(runtime_paths).

    %APPDATA%\\AI영상제작소\\credentials\\

프로그램 안에 묶지 않는다. 묶으면 client_secret과 refresh_token이
exe에 박혀 모두에게 함께 퍼진다(spec이 credentials/를 일부러 빼 둔
이유다). 사람이 제 자리에 두는 것이고, 없으면 없다고 말한다.

찾는 순서
---------
    1. 환경 변수                사람이 직접 가리킨 것 - 언제나 이긴다
    2. 저장소의 credentials/    개발 중. 실제로 있을 때만
    3. 사용자 자리              묶인 프로그램. 없어도 이 경로를 돌려준다

셋째가 "없어도 돌려준다"인 것이 중요하다. 화면이 그 경로를 그대로
보여 주어야 사람이 어디에 파일을 두면 되는지 알 수 있다 - 예전에는
'credentials/client_secret.json'이라는 상대 경로만 보여 주었고, 그것은
받은 사람에게 아무 자리도 가리키지 않는 글자였다.
"""

import os

CREDENTIALS_DIRNAME = "credentials"


def user_dir() -> str:
    """사용자 자리의 자격증명 폴더. 만들지는 않는다."""

    from app import runtime_paths

    return os.path.join(runtime_paths.home(), CREDENTIALS_DIRNAME)


def repo_dir() -> str:
    """저장소의 자격증명 폴더(개발 중에 쓰던 그 자리)."""

    return CREDENTIALS_DIRNAME


def resolve(env_name: str, filename: str) -> str:
    """
    그 파일을 어디서 읽고 어디에 쓸 것인가.

    환경 변수가 언제나 이긴다 - 테스트와 운영이 그 문을 쓴다.
    """

    given = os.environ.get(env_name)

    if given:
        return given

    beside = os.path.join(repo_dir(), filename)

    if os.path.exists(beside):
        return beside

    return os.path.join(user_dir(), filename)


def ensure_user_dir() -> str:
    """
    쓸 수 있도록 폴더를 만들어 둔다.

    토큰을 저장하는 쪽이 부른다 - 첫 로그인 때 폴더가 없어서 실패하면
    사람은 무엇을 잘못했는지 알 수 없다.
    """

    where = user_dir()

    os.makedirs(where, exist_ok=True)

    return where
