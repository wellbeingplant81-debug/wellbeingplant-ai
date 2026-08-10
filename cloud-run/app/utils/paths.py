"""
Sprint211 - 경로를 재는 자 하나 (Epic 59, Phase 24).

같은 질문을 두 자리가 물었다.

    내 것이 프로그램 폴더 밖에 있는가

    beta_package_validation   Sprint210에서 commonpath로 고침
    beta_readiness            startswith 그대로

그래서 이웃인데 이름이 겹치는 폴더에서 둘이 다른 답을 냈다. 같은
화면에 두 답이 함께 뜬다 - `처음 사용자 테스트` 한 장 안에 나눠 줄
폴더와 Readiness가 같이 있다.

한 벌을 더 쓰지 않는다
----------------------
Sprint210에서 한 쪽만 고쳤더니 곧바로 이 스프린트가 필요해졌다. 같은
함수를 두 벌 두면 또 갈라진다. 그래서 한 자를 둘이 나눠 쓴다.

여기 사는 이유
--------------
프로세스도 파일도 건드리지 않는 순수한 함수다. app/utils 에 이미
atomic_write · asset_cache · subtitle_utils 가 같은 성격으로 있다.
"""

import os


def is_inside(child: str, parent: str) -> bool:
    """
    child가 parent 안에 있는가. 글자가 아니라 자리로 본다.

        C:\\Temp\\RC209-home 은 C:\\Temp\\RC209 로 시작하지만
        그 안에 있지 않다 - 이름이 겹치는 이웃일 뿐이다.

    commonpath는 조각 단위로 본다. 위 둘의 공통 자리는 C:\\Temp 이고
    그것은 …RC209 가 아니므로 밖이다.

    startswith로 같은 일을 하려면 구분자를 손으로 붙여야 하고
    (parent + os.sep), 그러면 드라이브 뿌리에서 어긋난다. 파이썬이
    이미 아는 일을 다시 짜지 않는다.

    대소문자와 상대 경로는 여기서 맞춘다 - 부르는 쪽마다 다르게
    맞추면 그것이 또 다른 갈라짐이 된다.
    """

    here = os.path.normcase(os.path.abspath(child))
    there = os.path.normcase(os.path.abspath(parent))

    try:
        return os.path.commonpath([here, there]) == there
    except ValueError:
        # 드라이브가 다르면 겹칠 수 없다. commonpath가 그때 던진다.
        return False
