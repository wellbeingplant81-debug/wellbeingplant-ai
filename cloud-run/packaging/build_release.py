"""
Sprint170 - 남에게 줄 것을 한 번에 짓는다 (Epic 58, Phase 2).

    python packaging/build_release.py

두 걸음이다
-----------
    1. pyinstaller가 exe를 묶는다        spec이 정한 대로
    2. release가 그 옆에 나머지를 놓는다  tools · assets · README

나누어 둔 이유는 둘째가 몇 초면 끝나기 때문이다. README 한 줄을 고칠
때마다 몇 분을 다시 묶을 이유가 없다 - 그때는 release.py만 부른다.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import release

from app import app_info

SPEC = os.path.join(HERE, app_info.NAME + ".spec")


def bundle() -> str:
    """exe를 묶어 받는 사람의 폴더 안에 바로 놓는다."""

    into = os.path.join(REPO, "dist", release.FOLDER)

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", SPEC, "--noconfirm",
         "--distpath", into,
         "--workpath", os.path.join(REPO, "build")],
        check=True, cwd=REPO,
    )

    return into


def main() -> int:
    into = bundle()

    print()
    print("  배포 폴더")

    release._report(*release.build(into))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
