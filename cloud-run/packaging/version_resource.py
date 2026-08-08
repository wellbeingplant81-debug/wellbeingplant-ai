"""
Sprint170 - exe가 제 판번호를 들고 있게 (Epic 58, Phase 2).

Windows는 파일 속성 창에서 판번호를 보여 준다. 받은 사람이 "어느 판을
쓰고 계십니까"라는 물음에 답할 수 있는 유일한 자리다 - 프로그램을
켜지 못하는 상황에서도 볼 수 있는 것은 그것뿐이다.

PyInstaller는 이 정보를 파이썬 코드처럼 생긴 파일로 받는다. 그 글을
여기서 짓고, 값은 app_info 하나에서만 온다.

읽는 쪽도 여기 둔다
-------------------
만든 뒤에 실제로 들어갔는지 보려면 exe 안을 읽어야 한다. Windows의
version.dll이 해 주는 일이라 다른 패키지를 들이지 않는다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app_info

FILENAME = "version_info.txt"

# 한국어(0x0412) · UTF-16(1200). 문자열표의 이름이 이 둘로 정해진다.
LANGUAGE = 0x0412
CODEPAGE = 1200


def numbers() -> tuple:
    """
    Windows가 쓰는 네 자리 판번호.

    우리 판번호는 세 자리이므로 마지막은 0이다 - 없는 자리를 지어
    내지 않는다.
    """

    return tuple(int(part) for part in app_info.VERSION.split(".")) + (0,)


def _table() -> list:
    """
    파일 속성 창에 뜨는 것들.

    회사 이름은 적지 않는다 - 없는 회사를 지어 낼 수 없다.
    """

    exe = app_info.NAME + ".exe"

    return [
        ("FileDescription", app_info.NAME),
        ("FileVersion", app_info.VERSION),
        ("InternalName", app_info.NAME),
        ("OriginalFilename", exe),
        ("ProductName", app_info.NAME),
        ("ProductVersion", app_info.VERSION),
    ]


def text() -> str:
    """PyInstaller에게 줄 글."""

    strings = ",\n".join(
        f"                StringStruct('{key}', '{value}')"
        for key, value in _table()
    )

    return f"""# 자동 생성 - packaging/version_resource.py가 짓는다.
# 값은 app/app_info.py에서만 온다. 여기를 손으로 고치지 않는다.
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers={numbers()},
        prodvers={numbers()},
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable(
                '{LANGUAGE:04x}{CODEPAGE:04x}',
                [
{strings},
                ],
            ),
        ]),
        VarFileInfo([VarStruct('Translation', [{LANGUAGE}, {CODEPAGE}])]),
    ],
)
"""


def write(folder: str) -> str:
    """그 글을 파일로 적고 자리를 돌려준다."""

    os.makedirs(folder, exist_ok=True)

    path = os.path.join(folder, FILENAME)

    with open(path, "w", encoding="utf-8") as f:
        f.write(text())

    return path


def read_from(exe_path: str) -> dict:
    """
    만든 exe 안에 실제로 무엇이 들어갔는가.

    Windows가 파일 속성 창에서 읽는 그 자리를 그대로 읽는다. 못 읽으면
    빈 것 - 없는 것을 있다고 하지 않는다.
    """

    import ctypes
    import ctypes.wintypes as wintypes

    version = ctypes.WinDLL("version")

    size = version.GetFileVersionInfoSizeW(exe_path, None)

    if not size:
        return {}

    buffer = ctypes.create_string_buffer(size)

    if not version.GetFileVersionInfoW(exe_path, 0, size, buffer):
        return {}

    found = {}

    for key, _ in _table():
        block = f"\\StringFileInfo\\{LANGUAGE:04x}{CODEPAGE:04x}\\{key}"

        value = ctypes.c_wchar_p()
        length = wintypes.UINT()

        ok = version.VerQueryValueW(
            buffer, block, ctypes.byref(value), ctypes.byref(length))

        if ok and value.value:
            found[key] = value.value

    return found
