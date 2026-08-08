"""
Sprint169 - ffmpeg와 ffprobe를 어디서 찾는가 (Epic 58, Phase 1).

지금까지는 "ffmpeg"라고만 적어 PATH에 맡겼다. 개발하는 사람의 PC에는
깔려 있으니 그것으로 됐다.

실행 파일을 받은 사람에게는 없다
--------------------------------
그때 나는 오류는 FileNotFoundError뿐이고, 사람은 무엇을 깔아야
하는지 알 수 없다.

찾는 순서
---------
    1. AI_STUDIO_FFMPEG / AI_STUDIO_FFPROBE   사람이 직접 가리킨 것
    2. 프로그램 옆의 ffmpeg 폴더               같이 묶어 보낸 것
    3. imageio-ffmpeg가 들고 있는 것           이미 있는 의존성이다
    4. PATH                                    개발 중에는 이것이 잡힌다

셋째가 중요하다. moviepy가 쓰는 imageio-ffmpeg는 이미 requirements에
있고 제 ffmpeg를 함께 들고 온다 - 따로 받아 넣지 않아도 되는 유일한
길이다.

ffprobe는 그 안에 없다
----------------------
imageio-ffmpeg는 ffmpeg만 들고 온다. 그래서 ffprobe는 옆에 두거나
PATH에 있어야 하고, 없으면 길이를 잴 수 없다.

없는 것을 있다고 하지 않는다 - available()이 무엇이 없는지 말하고,
화면과 실행 파일이 그것을 그대로 보여 준다.
"""

import os
import shutil

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# 사람이 직접 가리킬 때 쓰는 이름.
ENV = {FFMPEG: "AI_STUDIO_FFMPEG", FFPROBE: "AI_STUDIO_FFPROBE"}

# 프로그램 옆에 같이 보낼 때 두는 폴더.
BUNDLED_DIRNAME = "ffmpeg"


def _from_env(name: str):
    given = os.environ.get(ENV[name])

    return given if given and os.path.exists(given) else None


def _beside_program(name: str):
    """프로그램 옆의 ffmpeg 폴더."""

    from app import runtime_paths

    for base in (runtime_paths.bundle_root(),
                 os.path.dirname(runtime_paths.bundle_root())):
        found = os.path.join(base, BUNDLED_DIRNAME, name + ".exe")

        if os.path.exists(found):
            return found

    return None


def _from_imageio(name: str):
    """
    moviepy가 쓰는 그 ffmpeg.

    ffmpeg만 있다 - ffprobe는 들고 오지 않으므로 여기서 찾지 않는다.
    """

    if name != FFMPEG:
        return None

    try:
        import imageio_ffmpeg

        found = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

    return found if found and os.path.exists(found) else None


def resolve(name: str) -> str:
    """
    그 도구를 부를 때 쓸 이름이나 경로.

    못 찾으면 이름 그대로 돌려준다 - 예전과 같이 PATH에 맡기는
    것이고, 여기서 예외를 던지면 도구를 안 쓰는 자리까지 죽는다.
    """

    for look in (_from_env, _beside_program, _from_imageio):
        found = look(name)

        if found:
            return found

    return shutil.which(name) or name


def available() -> dict:
    """
    지금 무엇을 쓸 수 있는가. {이름: 경로 또는 None}.

    화면과 실행 파일이 이것을 그대로 보여 준다 - 없는 것을 있다고
    하지 않는다.
    """

    found = {}

    for name in (FFMPEG, FFPROBE):
        path = resolve(name)

        found[name] = path if os.path.exists(path) or shutil.which(path) \
            else None

    return found


def missing() -> list:
    """없는 도구들. 비어 있으면 다 있다는 뜻이다."""

    return [name for name, path in available().items() if path is None]
