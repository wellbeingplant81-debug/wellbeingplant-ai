"""
Sprint170 - 첫 실행이 만들고, 갱신이 지우지 않는 것 (Epic 58, Phase 2).

새 판을 덮어씌우는 것이 곧 갱신이다. 그때 설정을 기본값으로 되돌리면,
쓰던 사람은 제가 바꾼 것이 사라진 것을 보게 된다.

그래서 규칙은 하나다
--------------------
    없는 것만 채운다.

첫 실행이면 전부 없으므로 전부 채워진다 - 그것이 "기본 설정 생성"이다.
두 번째부터는 채울 것이 없다. 판이 올라가면서 설정이 늘면 그 늘어난
것만 채운다.

모르는 열쇠는 지우지 않는다
---------------------------
사람이 손으로 넣어 둔 것일 수 있고, 다음 판이 쓸 것일 수도 있다.
우리가 모른다는 이유로 남의 것을 지우지 않는다.

여기 없는 것
------------
내 자료 폴더가 어디인지는 .workflow/free_workspace.json이 이미 들고
있다. 같은 사실을 두 자리에 적으면 어느 날 서로 다른 말을 한다.
"""

import json
import os

from app import app_info, runtime_paths

FILENAME = "settings.json"

# 브라우저를 켤 때 함께 열 것인가. 창에서 직접 주소를 여는 사람은
# 이것을 끈다.
OPEN_BROWSER = "open_browser"

# 어느 판이 이 자리를 만들었는가. 갱신을 알아보려면 필요하다.
CREATED_BY = "created_by_version"

DEFAULTS = {
    OPEN_BROWSER: True,
}


def path() -> str:
    """설정이 사는 자리."""

    return os.path.join(runtime_paths.home(), FILENAME)


def _read() -> dict:
    """
    적혀 있는 것. 읽지 못하면 빈 것.

    깨진 파일 하나 때문에 프로그램이 안 켜지면, 사람은 고칠 방법을
    알 수 없다 - 무엇이 잘못됐는지 볼 화면 자체가 안 뜬다.
    """

    try:
        with open(path(), encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        return {}

    return found if isinstance(found, dict) else {}


def load() -> dict:
    """
    지금 쓰는 값들. 적혀 있는 것이 먼저고, 없는 것만 기본값이다.

    파일을 만들지 않는다 - 읽기만 하는 자리가 파일을 쓰기 시작하면
    "첫 실행이 만든다"는 말이 어디서 일어난 일인지 알 수 없어진다.
    """

    found = dict(DEFAULTS)
    found.update(_read())

    return found


def save(changes: dict) -> dict:
    """
    바꿀 것만 바꾼다. 나머지는 적혀 있던 그대로.

    통째로 덮지 않는다 - 우리가 모르는 열쇠가 그때 사라진다.
    """

    from app.utils.atomic_write import atomic_write_json

    found = _read()
    found.update(changes or {})

    runtime_paths.ensure(runtime_paths.home())
    atomic_write_json(path(), found)

    return found


def ensure() -> dict:
    """
    첫 실행이 부르는 자리. 없는 것만 채우고 돌려준다.

    있던 값은 한 글자도 건드리지 않는다.

    적지 못해도 켜진다
    ------------------
    설정은 켜는 데 필요한 것이 아니라 편하자고 있는 것이다. 그것 하나
    때문에 프로그램이 안 켜지면, 사람은 화면을 보지도 못한 채로 무엇이
    잘못됐는지 알아내야 한다.

    감추지는 않는다 - 못 적었다고 말한다. 다음에 켤 때 바꾼 것이
    없어져 있으면 그것대로 놀란다.

    save()는 그대로 던진다. 사람이 고른 것을 못 적는 것은 다른 일이다 -
    화면이 "저장했습니다"라고 해 놓고 다음에 없으면 안 된다.
    """

    found = _read()

    missing = {k: v for k, v in DEFAULTS.items() if k not in found}

    if CREATED_BY not in found:
        missing[CREATED_BY] = app_info.VERSION

    if not missing:
        return found

    try:
        return save(missing)
    except Exception as failed:
        print(f"  [알림] 설정을 적지 못했습니다: {failed}")
        print(f"         {path()}")

        found.update(missing)

        return found
