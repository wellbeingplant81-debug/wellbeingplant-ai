"""
Sprint161 - 봤고 괜찮다는 말을 적어 둔다 (Epic 57, Phase 12).

Sprint160이 REVIEW를 만들었다. 없는 것은 아니지만 사람이 봐야 하는
것들이다 - 낱말 하나로만 걸렸거나, 여러 Scene이 같은 파일을 쓰거나.

그런데 사람이 보고 "이대로 괜찮다"고 해도 화면은 계속 검토 필요라고
했다. 볼 것이 하나라도 있으면 대시보드가 영영 노란색인 셈이다.

확인은 "무엇을"에 묶인다
------------------------
"이 scene은 괜찮다"가 아니다. "이 scene에 이 파일이 이런 까닭으로
걸린 것이 괜찮다"이다. 그래서 무엇을 확인했는지 함께 적는다.

    {"path": ..., "reasons": ["weak"], "confirmed_at": ..., "confirmed_by": ...}

그러면 두 가지가 저절로 풀린다.

    파일이 바뀌면      확인이 다른 파일을 가리키게 된다
    새 까닭이 생기면   사람이 아직 못 본 사실이다

첫째가 사양의 "파일을 바꾸면 review 자동 해제"다. 지우는 코드를 따로
두지 않는다 - 두면 지우는 자리를 빠뜨리는 날이 오고, 그때는 사람이
보지 않은 것이 확인된 것으로 남는다.

무엇도 바꾸지 않는다
--------------------
확인은 결정을 적을 뿐이다. 확인했다고 우리가 더 나은 파일로 바꿔
주면 사람이 확인한 것과 실제로 쓰이는 것이 달라진다.
"""

import json
import os

FILENAME = "review_confirmations.json"

VERSION = 1

# 지금은 사람뿐이다. asset_override와 같은 이유로 값을 미리 늘리지
# 않는다.
USER = "user"


def _path(project_path: str) -> str:
    return os.path.join(project_path, FILENAME)


def load(project_path: str) -> dict:
    """
    적어 둔 확인들. {scene 번호(문자열): {path, reasons, ...}}.

    깨져 있으면 빈 것으로 읽는다 - 확인 하나가 망가졌다고 화면 전체가
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

    read = {}

    for number, value in scenes.items():
        if not isinstance(value, dict) or not value.get("path"):
            continue

        read[str(number)] = {
            "path": value["path"],
            "reasons": [r for r in (value.get("reasons") or [])
                        if isinstance(r, str)],
            "confirmed_at": value.get("confirmed_at"),
            "confirmed_by": value.get("confirmed_by"),
        }

    return read


def for_scene(project_path: str, number):
    """그 scene에 적어 둔 확인. 없으면 None."""

    return load(project_path).get(str(number))


def _write(project_path: str, scenes: dict) -> dict:
    from app.utils.atomic_write import atomic_write_json

    atomic_write_json(
        _path(project_path), {"version": VERSION, "scenes": scenes},
    )

    return scenes


def save(project_path: str, number, path: str, reasons,
         confirmed_by: str = USER, confirmed_at: str = None) -> dict:
    """
    이 scene의 이 파일을 이 까닭으로 봤고 괜찮다.

    여기서 확인해도 되는 상황인지 보지 않는다 - 그 판정은 라우터가
    한다. 이 자리는 적기만 한다.
    """

    from datetime import datetime

    scenes = load(project_path)
    scenes[str(number)] = {
        "path": path,
        "reasons": sorted(reasons or []),
        "confirmed_at": confirmed_at or datetime.now().isoformat(
            timespec="seconds"),
        "confirmed_by": confirmed_by,
    }

    return _write(project_path, scenes)


def clear(project_path: str, number) -> dict:
    """확인을 지운다. 그러면 다시 검토 필요가 된다."""

    scenes = load(project_path)
    scenes.pop(str(number), None)

    return _write(project_path, scenes)


def covers(confirmation: dict, path: str, reasons) -> bool:
    """
    적어 둔 확인이 지금 상황을 덮는가.

    같은 파일이어야 하고, 지금의 까닭이 그때 본 까닭 안에 들어야
    한다. 새 까닭이 생겼으면 사람이 아직 못 본 사실이다.
    """

    if not confirmation or not path:
        return False

    if os.path.normcase(confirmation["path"]) != os.path.normcase(path):
        return False

    return set(reasons or []) <= set(confirmation.get("reasons") or [])
