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


def program_dir() -> str:
    """
    사람이 받은 폴더. exe가 실제로 놓인 자리다.

    bundle_root()와 다르다
    ----------------------
    묶인 프로그램에서 bundle_root()는 켤 때마다 새로 생기는 임시
    폴더(_MEIPASS)다. 사람이 거기에 무엇을 둘 수 없고, 끄면 사라진다.

    옆에 함께 보낸 것(tools/ 같은)을 찾으려면 이 자리라야 한다 -
    Sprint169는 이 구분이 없어서, 옆에 두고 찾는 길이 아예 없었다.

    개발 중에는 저장소다.
    """

    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))

    return bundle_root()


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


# Sprint172 - 배경 음악.
#
# 사용자 자리에서 이 이름으로 찾는다. 사람이 탐색기에서 열어 mp3를
# 떨어뜨릴 자리다.
MUSIC_DIRNAME = "music"

# 분류하지 않은 곡이 들어가는 자리. 고르는 쪽(bgm_service)이 정한
# 이름이고, 여기서 새로 짓지 않는다 - 두 자리가 다른 이름을 쓰면
# 넣어 둔 곳과 찾는 곳이 어긋난다.
#
# 그 합의는 test_release_candidate가 못으로 박아 둔다.
MUSIC_INBOX = "inbox"

# 다른 자리를 쓰고 싶을 때 주는 환경변수.
BGM_ENV = "AI_STUDIO_BGM"

# Sprint174 - 겪은 일을 적어 두는 자리.
#
# 사용자 자리 아래다. 프로그램 폴더에 두면 새 판을 덮어씌울 때 함께
# 사라지고, 그때 사라지는 것은 우리가 아직 못 읽은 이야기다.
FEEDBACK_DIRNAME = "feedback"


def feedback_root() -> str:
    """적어 둔 것이 사는 곳."""

    return os.path.join(home(), FEEDBACK_DIRNAME)


def _pickable(folder: str) -> bool:
    """그 폴더 바로 아래에 mp3가 있는가."""

    try:
        names = os.listdir(folder)
    except OSError:
        return False

    return any(
        name.lower().endswith(".mp3")
        and os.path.isfile(os.path.join(folder, name))
        for name in names
    )


def _has_music(path: str) -> bool:
    """
    고르는 쪽이 여기서 한 곡이라도 고를 수 있는가.

    "mp3가 어딘가 있는가"가 아니다 - 그렇게 세면 아무 데나 떨어뜨려
    놓고 "있다"고 말한 뒤, 몇 분을 쓴 렌더가 마지막에 죽는다(실제로
    한 번 그랬다). 고르는 쪽이 실제로 보는 자리만 센다.

        <root>/inbox/*.mp3        분류하지 않은 것
        <root>/<카테고리>/*.mp3   분류해 둔 것

    아래로 더 파고들지 않는다 - 고르는 쪽도 그러지 않는다.
    """

    if _pickable(os.path.join(path, MUSIC_INBOX)):
        return True

    try:
        names = os.listdir(path)
    except OSError:
        return False

    return any(
        _pickable(os.path.join(path, name))
        for name in names
        if os.path.isdir(os.path.join(path, name))
    )


def music_root() -> str:
    """
    배경 음악을 어디서 가져오는가.

    왜 이 함수가 생겼는가
    ---------------------
    렌더는 마지막에 BGM을 반드시 하나 고른다. 그 자리가 여태 프로그램
    안의 assets/music 하나뿐이었고, 묶으면 그것이 켤 때마다 새로 풀리는
    임시 폴더가 된다 - 사람이 넣을 수 없는 자리다. 그래서 묶은
    프로그램은 렌더를 단 한 번도 끝내지 못했다(Sprint171 실측).

    무엇을 함께 보낼지는 우리가 정하지 않는다
    -----------------------------------------
    저장소의 assets/music은 2.9GB에 남의 이름이 붙은 트랙들이다.
    그것을 남에게 재배포하는 일은 코드가 대신 정할 수 없고, 소리를
    하나 지어 넣는 것도 하지 않는다 - 삐 소리를 배경 음악이라고
    부르는 것은 되는 척이다.

    대신 사람이 넣을 자리를 만들고, 켤 때 그 자리를 말한다.

    보는 순서
    ---------
        1. AI_STUDIO_BGM            사람이 직접 가리킨 것
        2. <사용자 자리>/music       사람이 넣어 둔 것
        3. <프로그램>/assets/music   함께 묶여 온 것(PACKAGING_BGM)
        4. <사용자 자리>/music       아직 없을 때 - 넣을 자리를 가리킨다

    둘째가 셋째보다 앞이다 - 함께 보낸 것이 있더라도, 사람이 제 손으로
    넣은 것을 우리가 덮지 않는다.

    개발 중에는 예전 그대로다. 저장소의 assets/music에 이미 음악이
    있으므로 셋째에서 잡힌다 - 여기서 자리가 바뀌면 어제까지 만들던
    영상의 배경 음악이 통째로 사라진 것처럼 보인다.
    """

    given = os.environ.get(BGM_ENV)

    if given:
        return given

    mine = os.path.join(home(), MUSIC_DIRNAME)

    if _has_music(mine):
        return mine

    packed = os.path.join(bundle_root(), "assets", MUSIC_DIRNAME)

    if _has_music(packed):
        return packed

    return mine
