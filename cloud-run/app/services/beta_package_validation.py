"""
Sprint201 - 받은 사람의 자리에 있어야 할 것이 있는가 (Epic 59, Phase 19).

Sprint191~200은 기록을 읽었다. 이번은 디스크를 본다.

만들지 않는다
-------------
이 파일에서 가장 쉽게 어길 수 있는 것이다. "없으면 만들어 주면 친절하지
않은가"는 검증이 아니라 설치다. 확인하러 갔다가 자리를 만들어 버리면,
그 다음부터는 무엇이 원래 있던 것인지 알 수 없다.

그래서 여기에는 만드는 코드도 쓰는 코드도 없다. 테스트가 소스를 AST로
보고, 두 번 불러도 디스크가 그대로인지 확인한다.

packaging을 import하지 않는다
-----------------------------
release.py는 배포 폴더 밖에 남는다 - 묶인 프로그램 안에 없다. import
하면 정작 받은 사람의 자리에서 터진다.

그래서 이름을 여기에 둔다. 짓는 쪽과 어긋나면 테스트가 알려 준다
(test_the_names_match_the_packaging_shape).

켜 봤다고 말하지 않는다
-----------------------
이 표가 말할 수 있는 것은 "켜는 데 필요한 것이 갖춰져 있는가"까지다.
두 번 눌러 화면이 뜨는지는 사람이 봐야 한다. 그 사실을 note가 직접
말한다 - 안 그러면 이 표가 "켜진다"는 뜻으로 읽힌다.

아직 안 켠 자리에서 없는 것은 X가 아니다
----------------------------------------
내 자료 폴더들은 처음 켤 때 생긴다. 켜기 전에 없는 것은 정상이므로
"아직 없습니다"라고 적는다. X로 찍으면 고장 난 것으로 읽힌다.
"""

import datetime
import os

from app import app_info, runtime_paths
from app.services import media_tools

# 받는 사람이 푸는 폴더에 무엇이 있어야 하는가.
#
# packaging/release.py 의 SHAPE 와 같아야 한다. 그쪽을 import하지
# 않는 이유는 위에 적었고, 어긋나면 테스트가 잡는다.
SHAPE = {
    "executable": app_info.NAME + ".exe",
    "tools": media_tools.BESIDE_DIRNAME,
    "assets": "assets",
    "readme": "README.txt",
}

NOTE = (
    "받은 폴더와 내 자료 자리를 살펴본 것입니다. 프로그램을 켜 보지는 "
    "않았습니다 - 두 번 눌러 화면이 뜨는지는 직접 확인하셔야 합니다."
)

NOT_YET = "아직 없습니다. 처음 켤 때 만들어집니다."


def _row(key, label, ok, detail):
    return {"key": key, "label": label, "ok": ok, "detail": detail}


def _package(folder: str) -> list:
    """받은 폴더에 넷이 다 있는가."""

    checks = []

    for key, label in (("executable", "실행파일"),
                       ("tools", "도구 폴더"),
                       ("assets", "예시 자료"),
                       ("readme", "안내문")):
        name = SHAPE[key]
        there = os.path.exists(os.path.join(folder, name))

        checks.append(_row(key, label, there,
                           f"{name} 이(가) {'있습니다' if there else '없습니다'}."))

    checks.append(_row(
        "version", "판번호", _readme_says_version(folder),
        f"안내문에 {app_info.VERSION} 이(가) 적혀 있는지 봅니다."))

    return checks


def _readme_says_version(folder: str) -> bool:
    """안내문이 지금 판번호를 말하는가."""

    path = os.path.join(folder, SHAPE["readme"])

    if not os.path.isfile(path):
        return False

    try:
        # 읽기만 한다. 모드를 주지 않으면 "r"이고, 테스트가 이 파일의
        # 모든 open이 쓰기가 아닌지 확인한다.
        with open(path, encoding="utf-8", errors="replace") as f:
            return app_info.VERSION in f.read(4096)
    except OSError:
        return False


def _first_run() -> list:
    """처음 켜면 생기는 자리들. 없다고 고장 난 것이 아니다."""

    # music_root()가 아니라 내 자리 밑을 본다.
    #
    # music_root()는 "어디서 음악을 읽는가"이고, 개발 중에는 저장소의
    # assets/music으로 떨어진다. 여기서 알고 싶은 것은 README가 사용자에게
    # 알려 주는 "넣는 자리"이고 그것은 언제나 내 자리 밑이다. 둘을 섞으면
    # 아직 안 켠 자리에서도 "있습니다"가 나온다(실측에서 그랬다).
    music = os.path.join(runtime_paths.home(), runtime_paths.MUSIC_DIRNAME,
                         runtime_paths.MUSIC_INBOX)

    places = (
        ("data_home", "내 자료 자리", runtime_paths.home()),
        ("output", "만든 영상", runtime_paths.output_root()),
        ("dataset", "쌓인 기록", runtime_paths.dataset_root()),
        ("workflow", "고른 자료 폴더", runtime_paths.workflow_root()),
        ("feedback", "겪은 일 적는 자리", runtime_paths.feedback_root()),
        ("music_inbox", "배경 음악 넣는 자리", music),
    )

    checks = [
        _row(key, label, True, "있습니다.") if os.path.isdir(where)
        else _row(key, label, None, NOT_YET)
        for key, label, where in places
    ]

    from app import settings

    kept = os.path.join(runtime_paths.home(), settings.FILENAME)

    checks.append(
        _row("settings", "설정", True, "있습니다.") if os.path.isfile(kept)
        else _row("settings", "설정", None, NOT_YET))

    return checks


def _runtime(folder: str) -> list:
    """도구가 있는가, 그리고 그것이 받은 폴더 안의 것인가."""

    gone = media_tools.missing()

    checks = [
        _row(name, name, name not in gone,
             "없습니다." if name in gone else "있습니다.")
        for name in (media_tools.FFMPEG, media_tools.FFPROBE)
    ]

    # Sprint211 - 여기도 startswith 였다. _user 와 같은 결함이다 -
    # tools 옆에 toolsX 같은 이웃이 있으면 그 안의 것을 "받은 폴더
    # 안"이라고 본다. 재는 자를 하나로 만든 김에 여기도 그것을 쓴다.
    from app.utils.paths import is_inside

    beside = os.path.join(folder, media_tools.BESIDE_DIRNAME)

    inside = []

    for name in (media_tools.FFMPEG, media_tools.FFPROBE):
        where = media_tools.resolve(name)
        inside.append(is_inside(where, beside) if where else False)

    all_inside = inside and False not in inside

    checks.append(_row(
        "beside", "PATH에 기대지 않음", all_inside,
        "받은 폴더 안의 도구를 쓰고 있는지 봅니다 - PATH에서 찾아 쓰면 "
        "그 PC에서만 됩니다."))

    return checks


def _user(folder: str) -> list:
    """내 것과 프로그램 자리가 갈려 있는가."""

    # Sprint211 - 재는 자는 app/utils/paths 에 하나만 둔다. 여기에
    # 한 벌을 더 쓰면 beta_readiness와 또 갈라진다(Sprint210에서
    # 그렇게 갈라졌다). 대소문자와 상대 경로도 그쪽에서 맞춘다.
    from app.utils.paths import is_inside

    home = runtime_paths.home()

    return [
        _row("separated", "사용자 데이터 분리",
             not is_inside(home, runtime_paths.program_dir()),
             "내 것이 프로그램 폴더 밖에 있는지 봅니다."),
        _row("no_write", "프로그램 폴더에 안 쌓임",
             not is_inside(home, folder),
             "받은 폴더 안에 내 자리가 생기지 않았는지 봅니다."),
    ]


def _text(found: dict) -> str:
    """붙여 넣을 글. 여기서 새로 판정하지 않는다."""

    marks = {True: "O", False: "X", None: "?"}

    lines = [f"{app_info.NAME} 패키지 확인",
             "",
             f"판번호     {found['version']}",
             f"확인 시점  {found['taken_at']}",
             ""]

    for group in found["groups"]:
        lines.append(group["label"])

        for row in group["checks"]:
            lines.append(f"  {marks[row['ok']]} {row['label']} - "
                         f"{row['detail']}")

        lines.append("")

    lines.append(found["note"])

    return "\n".join(lines)


def build(folder: str = None) -> dict:
    """
    받은 폴더와 내 자리를 살펴본다. 읽기만 하고 만들지 않는다.

    folder를 주지 않으면 지금 이 프로그램이 있는 자리를 본다.
    """

    where = folder or runtime_paths.program_dir()

    groups = [
        {"key": "package", "label": "받은 폴더", "checks": _package(where)},
        {"key": "first_run", "label": "처음 켜면 생기는 자리",
         "checks": _first_run()},
        {"key": "runtime", "label": "도구", "checks": _runtime(where)},
        {"key": "user", "label": "내 것과 프로그램 자리",
         "checks": _user(where)},
    ]

    rows = [row for group in groups for row in group["checks"]]

    found = {
        "taken_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "version": app_info.VERSION,
        "groups": groups,
        "passed": sum(1 for row in rows if row["ok"] is True),
        "failed": sum(1 for row in rows if row["ok"] is False),
        "unknown": sum(1 for row in rows if row["ok"] is None),
        "note": NOTE,
    }

    found["report"] = _text(found)

    return found
