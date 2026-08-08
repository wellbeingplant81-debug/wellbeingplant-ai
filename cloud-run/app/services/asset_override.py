"""
Sprint158 - 사람이 고른 것을 적어 둔다 (Epic 57, Phase 9).

Sprint157이 "왜 걸렸는지"를 말하게 했다. 사람은 1/8로 걸린 것을
알아볼 수 있게 됐지만, 알아본 다음에 할 수 있는 일이 없었다 - 파일
이름을 고쳐 다시 훑는 것뿐이었다.

여기에 적히는 것은 사람의 결정뿐이다
------------------------------------
Sprint84가 정한 원칙이다. 산출물에서 읽을 수 있는 것은 읽고, 사람이
정한 것만 적는다. "이 scene에는 이 파일을 쓰겠다"는 어디서도 읽어
낼 수 없으므로 여기 적는다.

    {"version": 1, "scenes": {"1": "D:/자료/images/자연광.png"}}

경로를 적는다 - 이름만 적으면 폴더가 다른 같은 이름을 구분하지
못한다.

자동으로 지우지 않는다
----------------------
자료가 늘어 더 잘 맞는 것이 생겨도 우리가 바꾸지 않는다. 사람이
정한 것이 조용히 사라지면, 다음에 열었을 때 왜 다른 그림이 나오는지
알 수 없다.

다만 그 파일이 사라졌으면 쓸 수가 없다. 그때는 자동으로 고른 것으로
돌아가되, 무엇이 사라졌는지 말한다 - 조용히 넘어가면 사람은 자기가
고른 것이 쓰이고 있다고 믿는다.
"""

import json
import os

FILENAME = "asset_overrides.json"

VERSION = 1


def _path(project_path: str) -> str:
    return os.path.join(project_path, FILENAME)


def load(project_path: str) -> dict:
    """
    적어 둔 결정들. {scene 번호(문자열): 경로}.

    깨져 있으면 빈 것으로 읽는다 - 결정 하나가 망가졌다고 화면 전체가
    죽을 이유는 없다.
    """

    try:
        with open(_path(project_path), encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        return {}

    if not isinstance(found, dict):
        return {}

    scenes = found.get("scenes")

    if not isinstance(scenes, dict):
        return {}

    return {
        str(number): path
        for number, path in scenes.items()
        if isinstance(path, str) and path
    }


def for_scene(project_path: str, number):
    """그 scene에 사람이 정한 경로. 없으면 None."""

    return load(project_path).get(str(number))


def save(project_path: str, number, path: str) -> dict:
    """
    이 scene에는 이것을 쓰겠다.

    여기서 그 경로가 쓸 만한지 보지 않는다 - 무엇이 목록에 있는가는
    라우터가 판정한다. 이 자리는 적기만 한다.
    """

    scenes = load(project_path)
    scenes[str(number)] = path

    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(
        _path(project_path), {"version": VERSION, "scenes": scenes},
    )

    return scenes


def clear(project_path: str, number) -> dict:
    """사람이 정한 것을 지운다. 그러면 자동으로 고른 것으로 돌아간다."""

    scenes = load(project_path)
    scenes.pop(str(number), None)

    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(
        _path(project_path), {"version": VERSION, "scenes": scenes},
    )

    return scenes


def missing(project_path: str) -> dict:
    """
    정해 뒀는데 그 파일이 사라진 것들. {scene 번호: 경로}.

    화면이 이것을 그대로 말한다 - 조용히 다른 그림으로 바뀌면 사람은
    자기가 고른 것이 쓰이고 있다고 믿는다.
    """

    return {
        number: path
        for number, path in load(project_path).items()
        if not os.path.exists(path)
    }
