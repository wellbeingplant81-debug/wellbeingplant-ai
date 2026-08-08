"""
Sprint169 - 프로그램과 사용자 것을 가른다 (Epic 58, Phase 1).

지금까지는 저장소 안에서만 돌았다. 그래서 프로젝트도, 승인 기록도,
축적 데이터도 전부 코드 옆에 쌓였다 - 개발 중에는 편하다.

실행 파일로 묶으면 그 자리가 읽기 전용이 된다
---------------------------------------------
PyInstaller로 묶은 exe는 실행할 때 임시 폴더에 풀린다. 거기에 쓰면
프로그램을 끌 때 같이 사라지고, Program Files에 설치했다면 아예 쓸
수도 없다.

그래서 사용자 것은 사용자 자리에 둔다.

    개발 중    저장소 그대로 - 지금과 한 글자도 다르지 않다
    묶였을 때  %APPDATA%\\AI영상제작소

무엇이 사용자 것인가
--------------------
    output/     만든 영상들
    .workflow/  승인·내 자료 폴더 같은 사람의 결정
    .dataset/   쌓아 온 관측 기록

코드와 static은 프로그램 것이므로 묶인 자리에 그대로 둔다.

바꿀 수 있게 둔다
-----------------
AI_STUDIO_HOME을 주면 그쪽을 쓴다. 옮기고 싶은 사람, 두 벌을 따로
쓰고 싶은 사람, 그리고 테스트가 이 문을 쓴다 - 테스트가 사용자의
실제 자리에 쓰면 그 사람의 프로젝트를 건드리게 된다.
"""

import os
import sys

# 사용자 것이 사는 폴더 이름. 사람이 탐색기에서 찾을 이름이다.
APP_DIRNAME = "AI영상제작소"

# 이 자리를 바꾸고 싶을 때 주는 환경변수.
HOME_ENV = "AI_STUDIO_HOME"


def is_frozen() -> bool:
    """실행 파일로 묶여 도는가."""

    return bool(getattr(sys, "frozen", False))


def bundle_root() -> str:
    """
    프로그램이 사는 자리. 코드와 static이 여기 있다.

    묶였으면 PyInstaller가 풀어 둔 임시 폴더(_MEIPASS)이고, 아니면
    저장소다. 여기에는 쓰지 않는다 - 읽기만 한다.
    """

    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))

    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _appdata() -> str:
    """
    Windows가 프로그램마다 쓰라고 내주는 자리.

    없으면(다른 OS이거나 환경이 이상하면) 홈 아래로 간다 - 못 쓰는
    자리를 골라 놓고 나중에 조용히 실패하는 것보다 낫다.
    """

    found = os.environ.get("APPDATA")

    if found and os.path.isdir(found):
        return found

    return os.path.expanduser("~")


def home() -> str:
    """
    사용자 것이 사는 자리.

    개발 중에는 저장소다 - 지금까지 쌓인 것을 그대로 쓴다. 여기서
    자리를 옮기면 어제까지 만든 프로젝트가 사라진 것처럼 보인다.
    """

    given = os.environ.get(HOME_ENV)

    if given:
        return given

    if is_frozen():
        return os.path.join(_appdata(), APP_DIRNAME)

    return bundle_root()


def ensure(path: str) -> str:
    """그 자리를 만들어 두고 돌려준다. 있으면 그대로."""

    os.makedirs(path, exist_ok=True)

    return path


def output_root() -> str:
    """만든 영상들이 사는 곳."""

    if os.environ.get(HOME_ENV) or is_frozen():
        return os.path.join(home(), "output")

    # 개발 중에는 예전 그대로 - 작업 디렉터리 기준 상대 경로다.
    return "output"


def dataset_root() -> str:
    """쌓아 온 관측 기록이 사는 곳."""

    return os.path.join(home(), ".dataset")


def workflow_root() -> str:
    """사람이 내린 결정들이 사는 곳(승인·내 자료 폴더)."""

    return os.path.join(home(), ".workflow")
