"""
Sprint169 - 함께 보낼 ffmpeg·ffprobe를 어느 자리에 놓는가 (Epic 58).
Sprint170 - 그 자리가 exe 옆의 tools/가 됐다.

왜 spec 안에 두지 않는가
------------------------
spec은 pyinstaller가 제 방식으로 읽는 파일이라 테스트가 부를 수 없다.
그래서 처음 만든 exe는 두 도구를 엉뚱한 자리에 넣고도 초록불이었다 -
테스트가 본 것은 개발 PC의 PATH였고, 그 PC에는 둘 다 깔려 있었다.

    번들 안에 실제로 생긴 것   ffmpeg\\ffprobe.exe\\ffprobe.exe
    media_tools가 보는 자리    ffmpeg\\ffprobe.exe

한 글자 차이가 "음성 길이를 못 잰다"로 끝났다. 그래서 자리를 정하는
일을 여기로 꺼내 두고, 테스트가 그 자리를 직접 본다.

Sprint170 - 안에 넣지 않고 옆에 둔다
------------------------------------
배포 구조가 tools/를 정했다. 옆에 두면

    exe가 가벼워진다           200MB가 넘던 것에서 도구가 빠진다
    사람이 바꿔 넣을 수 있다   제 ffmpeg를 쓰고 싶은 사람이 있다

대신 폴더가 흩어지면 못 찾는다. 그때 프로그램은 켜지면서 무엇이
없는지 말하고, README가 폴더를 통째로 두라고 말한다 - 조용히
실패하지 않는다.

이름을 바꿔 담는다
------------------
imageio-ffmpeg가 들고 있는 것은 ffmpeg-win-x86_64-v7.1.exe 같은
판번호가 붙은 이름이다. media_tools는 ffmpeg.exe를 찾으므로 그
이름으로 복사한다.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import media_tools

# 가진 사람이 ffprobe의 자리를 가리킬 때 쓰는 이름.
FFPROBE_ENV = "PACKAGING_FFPROBE"


def landing(name: str) -> str:
    """
    받은 폴더 안에서 이 도구가 놓일 자리(exe가 있는 자리로부터).

    media_tools가 보는 그 자리다 - 두 자리가 따로 정해지면 넣어
    놓고도 못 찾는다.
    """

    return os.path.join(media_tools.BESIDE_DIRNAME, name + ".exe")


def _imageio_ffmpeg():
    """moviepy가 쓰는 그 ffmpeg. 이미 있는 의존성이다."""

    try:
        import imageio_ffmpeg

        found = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

    return found if found and os.path.exists(found) else None


def sources() -> list:
    """
    무엇을 어디서 가져오는가. (이름, 있는 자리) 쌍.

    없는 것은 넣지 않는다 - 있는 척하지 않고, 켤 때 없다고 말한다.
    """

    found = []

    ffmpeg = _imageio_ffmpeg()

    if ffmpeg:
        found.append((media_tools.FFMPEG, ffmpeg))

    ffprobe = os.environ.get(FFPROBE_ENV)

    if ffprobe and os.path.exists(ffprobe):
        found.append((media_tools.FFPROBE, ffprobe))

    return found


def place(program_dir: str) -> list:
    """
    받은 폴더에 도구를 놓는다. 놓은 자리들을 돌려준다.

    자리는 landing()이 정한다 - 여기서 문자열을 다시 지으면 두 자리가
    또 어긋난다.
    """

    placed = []

    for name, source in sources():
        target = os.path.join(program_dir, landing(name))

        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)

        placed.append(target)

    return placed
