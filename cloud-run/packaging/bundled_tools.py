"""
Sprint169 - 함께 보낼 ffmpeg·ffprobe를 어느 자리에 놓는가 (Epic 58).

왜 spec 안에 두지 않는가
------------------------
spec은 pyinstaller가 제 방식으로 읽는 파일이라 테스트가 부를 수 없다.
그래서 처음 만든 exe는 두 도구를 엉뚱한 자리에 넣고도 초록불이었다 -
테스트가 본 것은 개발 PC의 PATH였고, 그 PC에는 둘 다 깔려 있었다.

    번들 안에 실제로 생긴 것   ffmpeg\\ffprobe.exe\\ffprobe.exe
    media_tools가 보는 자리    ffmpeg\\ffprobe.exe

PyInstaller의 binaries는 (어디 있는 것, **넣을 폴더**) 쌍이다. 둘째
자리에 파일 경로를 적으면 그 이름의 폴더가 생긴다. 한 글자 차이가
"길이를 못 잰다"로 끝났다.

여기로 꺼내 두면 그 자리를 테스트가 직접 볼 수 있다.

이름을 바꿔 담는다
------------------
imageio-ffmpeg가 들고 있는 것은 ffmpeg-win-x86_64-v7.1.exe 같은
판번호가 붙은 이름이다. media_tools는 ffmpeg.exe를 찾으므로, 묶기
전에 그 이름으로 복사해 둔다.
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
    묶인 프로그램 안에서 이 도구가 놓일 자리(뿌리로부터).

    media_tools._beside_program이 보는 그 자리다 - 두 자리가 따로
    정해지면 넣어 놓고도 못 찾는다.
    """

    return os.path.join(media_tools.BUNDLED_DIRNAME, name + ".exe")


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


def entries(staging: str) -> list:
    """
    PyInstaller의 binaries에 그대로 넣을 목록.

    둘째 값은 파일 이름이 아니라 **넣을 폴더**다. landing()이 정한
    자리에서 폴더만 떼어 쓴다 - 여기서 문자열을 다시 지으면 두 자리가
    또 어긋난다.
    """

    os.makedirs(staging, exist_ok=True)

    found = []

    for name, source in sources():
        staged = os.path.join(staging, os.path.basename(landing(name)))

        shutil.copyfile(source, staged)

        found.append((staged, os.path.dirname(landing(name))))

    return found
