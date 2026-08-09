"""
Sprint170 - 남에게 줄 폴더를 짓는다 (Epic 58, Phase 2).

    python packaging/release.py

받는 사람이 푸는 것
-------------------
    AI영상제작소/
      AI영상제작소.exe    프로그램
      tools/              ffmpeg · ffprobe
      assets/             예시 자료 폴더 틀
      README.txt          어떻게 켜고 내 것이 어디 쌓이는가

폴더를 통째로 둬야 한다
-----------------------
exe만 떼어 내면 tools/를 못 찾아 영상이 안 만들어진다. 그때 조용히
실패하지 않는다 - 켜면서 무엇이 없는지 말한다. README도 그렇게 적는다.

여기서 묶지 않는다
------------------
묶는 일은 pyinstaller가 spec으로 한다. 이 파일은 묶인 것 옆에 무엇을
놓을지만 정한다 - 한 파일이 둘 다 하면 어느 쪽이 틀렸는지 알기
어려워진다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bundled_tools

from app import app_info, runtime_paths
from app.services import media_tools

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 받는 사람이 푸는 폴더의 이름.
FOLDER = app_info.NAME

TOOLS_DIRNAME = media_tools.BESIDE_DIRNAME
ASSETS_DIRNAME = "assets"
README_FILENAME = "README.txt"

# 그 폴더에 무엇이 있어야 하는가. (이름, 어디서 오는가)
SHAPE = (
    (app_info.NAME + ".exe", "pyinstaller가 묶은 것"),
    (TOOLS_DIRNAME, "ffmpeg · ffprobe"),
    (ASSETS_DIRNAME, "예시 자료 폴더 틀"),
    (README_FILENAME, "release.readme()"),
)

# 자료를 어느 폴더에 넣어야 하는지가 곧 종류다(local_library).
EXAMPLE_FOLDERS = ("images", "videos", "voices", "music")


def readme() -> str:
    """
    받은 사람이 처음 읽는 글.

    아는 것만 적는다 - 무엇이 되는지, 무엇이 안 되는지, 내 것이 어디에
    쌓이는지.
    """

    made = app_info.build_date()

    return f"""{app_info.NAME} {app_info.VERSION}
{"빌드 " + made if made else ""}

켜는 법
-------
{app_info.NAME}.exe 를 두 번 누르십시오.
검은 창이 뜨고, 잠시 뒤 브라우저에 화면이 열립니다.
열리지 않으면 창에 찍힌 주소를 직접 여십시오.

끄려면 그 창을 닫거나 Ctrl+C 를 누르십시오.

이 폴더는 통째로 두십시오
-------------------------
{TOOLS_DIRNAME}\\ 안에 영상을 만드는 데 필요한 ffmpeg 와 ffprobe 가
있습니다. {app_info.NAME}.exe 만 다른 곳으로 옮기면 그것을 찾지 못해
영상이 만들어지지 않습니다.

없으면 켤 때 창이 알려 줍니다. 조용히 실패하지 않습니다.

배경 음악을 먼저 넣으십시오
---------------------------
영상에는 배경 음악이 하나 깔립니다. 이 프로그램에는 음악이 들어 있지
않습니다 - 남의 곡을 함께 배포할 수 없기 때문입니다.

    %APPDATA%\\{runtime_paths.APP_DIRNAME}\\{runtime_paths.MUSIC_DIRNAME}\\{runtime_paths.MUSIC_INBOX}

이 폴더에 mp3 를 넣으십시오. 한 곡이면 됩니다. 폴더는 처음 켤 때
만들어져 있습니다.

넣지 않으면 자료 준비와 검사까지는 되지만 영상은 만들어지지 않고,
켤 때 창이 그 사실과 넣을 자리를 말합니다.

내가 만든 것은 어디에 쌓입니까
------------------------------
%APPDATA%\\{runtime_paths.APP_DIRNAME}

    output\\      만든 영상들
    {runtime_paths.MUSIC_DIRNAME}\\       내가 넣은 배경 음악
    .workflow\\   내가 고른 자료 폴더, 확인해 둔 것
    .dataset\\    쌓인 기록
    logs\\        켜지지 않았을 때의 기록
    settings.json  설정

프로그램 폴더 안에는 아무것도 쌓이지 않습니다. 새 판을 덮어씌워도
위의 것들은 그대로 남습니다.

내 자료로 만들기
----------------
API 키 없이 만들려면 자료를 폴더에 모아 두고 화면에서 그 폴더를
고르십시오. {ASSETS_DIRNAME}\\ 에 빈 틀이 들어 있습니다.

파일 이름이 곧 검색어입니다 - 프로그램은 그림 안을 들여다보지
않습니다. "무릎 스트레칭.png" 처럼 장면에 쓸 낱말을 이름에 넣으면
그 장면에 걸립니다.

음성은 번호로 찾습니다 - scene1.wav 는 1번 장면입니다.

문제가 생기면
-------------
화면 오른쪽 위 [정보 복사] 를 누르면 지금 쓰고 계신 판과 상태가
복사됩니다. 그것을 함께 보내 주시면 훨씬 빨리 찾습니다.

켜지지 않으면 %APPDATA%\\{runtime_paths.APP_DIRNAME}\\logs\\ 에 기록이
남습니다. 그 파일을 보내 주십시오.

겪으신 일을 적어 주십시오
-------------------------
    %APPDATA%\\{runtime_paths.APP_DIRNAME}\\{runtime_paths.FEEDBACK_DIRNAME}

이 폴더에 무엇이든 적어 두십시오. 무엇을 적으면 되는지는 그 안의
안내 파일에 있습니다. 새 판을 덮어씌워도 지워지지 않습니다.

문의
----
{app_info.CONTACT}
"""


def _example_note() -> str:
    return f"""여기에 자료를 모아 두십시오.

    images\\   그림 (png · jpg · webp · bmp)
    videos\\   영상 (mp4 · mov · mkv · webm · avi) - 첫 화면을 씁니다
    voices\\   목소리 (wav · mp3)
    music\\    배경음악

파일 이름이 곧 검색어입니다
---------------------------
프로그램은 그림 안을 들여다보지 않습니다. 이름에서 낱말을 끊어 내
장면의 문구와 겹치는 것을 고릅니다.

    무릎 스트레칭.png     "무릎"이나 "스트레칭"이 나오는 장면에 걸림
    거실 자연광.jpg       "거실" · "자연광"

이름을 잘 지으면 잘 찾히고, 아니면 잘 안 찾힙니다. 어느 낱말로
걸렸는지는 화면이 그대로 보여 줍니다.

목소리는 번호입니다
-------------------
    scene1.wav   1번 장면
    scene2.wav   2번 장면

없는 번호는 없다고 말합니다 - 다른 번호를 대신 넣지 않습니다.
"""


def build(into: str = None):
    """
    폴더를 짓고 (그 자리, 놓은 도구들)을 돌려준다.

    exe는 이미 그 안에 있어야 한다 - 묶는 일은 pyinstaller가 한다.
    """

    into = into or os.path.join(REPO, "dist", FOLDER)

    os.makedirs(into, exist_ok=True)

    placed = bundled_tools.place(into)

    examples = os.path.join(into, ASSETS_DIRNAME, "예시 자료")

    for name in EXAMPLE_FOLDERS:
        os.makedirs(os.path.join(examples, name), exist_ok=True)

    with open(os.path.join(examples, "읽어보기.txt"), "w",
              encoding="utf-8") as f:
        f.write(_example_note())

    with open(os.path.join(into, README_FILENAME), "w",
              encoding="utf-8") as f:
        f.write(readme())

    return into, placed


def _report(into, placed) -> None:
    print(f"  {into}")

    for name, _ in SHAPE:
        path = os.path.join(into, name)
        mark = "있음" if os.path.exists(path) else "없음"

        print(f"    {name:<24} {mark}")

    for path in placed:
        print(f"    {os.path.relpath(path, into):<24} "
              f"{os.path.getsize(path):,} 바이트")

    missing = [name for name, _ in SHAPE
               if not os.path.exists(os.path.join(into, name))]

    if missing:
        print()
        print("  아직 없는 것: " + ", ".join(missing))


if __name__ == "__main__":
    _report(*build())
