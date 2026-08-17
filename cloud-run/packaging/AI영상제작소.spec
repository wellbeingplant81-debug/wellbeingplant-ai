# -*- mode: python ; coding: utf-8 -*-
"""
Sprint169 - 무엇을 묶고 무엇을 두는가 (Epic 58, Phase 1).
Sprint170 - 판번호와 빌드 날짜를 함께 넣는다 (Phase 2).

    python packaging/build_release.py

무엇을 넣는가
-------------
    launcher.py       켜는 자리
    app/              코드
    app/static/       화면. 빠지면 화면이 통째로 안 뜬다
    app/prompts/      요청문 틀. 대본이 이것으로 만들어진다
    build_info.json   언제 묶었는가
    판번호            Windows 파일 속성 창이 읽는 자리

무엇을 넣지 않는가
------------------
    ffmpeg · ffprobe  exe 옆 tools/에 둔다(Sprint170 배포 구조)
    output/           만든 영상들 - 남의 것을 함께 배포하게 된다
    .workflow/        사람이 내린 결정
    .dataset/         쌓아 온 관측 기록
    credentials/      자격 증명
    .env              API 키

가운데 셋은 받는 사람의 자리(%APPDATA%)에 새로 생긴다. 뒤의 둘은
애초에 넣으면 안 되는 것이다 - 넣으면 키가 함께 퍼진다.

자리를 여기서 정하지 않는다
---------------------------
도구가 어디 놓이는지는 bundled_tools가, 판번호는 version_resource가
정한다. 이 파일은 pyinstaller만 읽을 수 있어서, 여기에 규칙을 적으면
아무도 그것을 검사하지 못한다 - 처음 만든 exe가 실제로 엉뚱한 자리에
넣고도 초록불이었다.
"""

import datetime
import json
import os
import sys

from PyInstaller.utils.hooks import copy_metadata

block_cipher = None

HERE = os.path.dirname(os.path.abspath(SPEC))
REPO = os.path.dirname(HERE)

sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import version_resource

from app import app_info

# 만드는 것만 두는 자리.
STAGING = os.path.join(REPO, "build", "묶을것")

os.makedirs(STAGING, exist_ok=True)

# 언제 묶었는가. 재는 것이지 정하는 것이 아니다 - 지금이 그 순간이다.
BUILD_INFO = os.path.join(STAGING, app_info.BUILD_FILENAME)

with open(BUILD_INFO, "w", encoding="utf-8") as f:
    json.dump(
        {"version": app_info.VERSION,
         "built_at": datetime.datetime.now().isoformat(timespec="seconds")},
        f, ensure_ascii=False)

binaries = []

datas = [
    (os.path.join(REPO, "app", "static"), "app/static"),
    (os.path.join(REPO, "app", "prompts"), "app/prompts"),
    (BUILD_INFO, "."),
]


def _given_music():
    """
    함께 묶을 배경 음악. 가리키지 않으면 넣지 않는다.

    렌더는 BGM을 반드시 하나 고르므로, 없으면 묶은 프로그램은 영상을
    끝까지 만들지 못한다(Sprint171 실측). 그런데 저장소의 assets/music은
    2.9GB이고 남의 이름이 붙은 트랙들이다 - 그것을 남에게 재배포하는
    일은 묶기 스크립트가 대신 정할 수 있는 것이 아니다.

    그래서 문만 만들어 둔다. PACKAGING_BGM에 폴더를 주면 그 폴더가
    assets/music이 된다. 무엇을 넣을지는 주는 사람이 정한다.

    없으면 넣지 않고, 프로그램이 켜질 때 없다고 말한다 - 있는 척하지
    않는다.
    """

    given = os.environ.get("PACKAGING_BGM")

    return [(given, "assets/music")] if given and os.path.isdir(given) else []


datas += _given_music()


def _metadata(*names):
    """
    패키지가 제 판번호를 물어볼 때 필요한 것.

    imageio는 켜지자마자 importlib.metadata.version("imageio")를
    부른다. 그 기록이 안 들어가면 화면이 뜨기도 전에 죽는다 -
    실제로 처음 만든 exe가 그렇게 죽었다.
    """

    found = []

    for name in names:
        try:
            found += copy_metadata(name)
        except Exception:
            # 없는 것을 넣으려다 묶기 자체가 멈추지 않게 한다.
            pass

    return found


datas += _metadata("imageio", "imageio_ffmpeg", "moviepy", "numpy")

# 늦게 들이는 것들. 코드가 문자열로 부르므로 PyInstaller가 스스로
# 찾지 못한다 - 빠지면 그 자리에서 ImportError가 난다.
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "app.providers.local_stock_provider",
    "app.providers.local_voice_provider",
    "app.providers.flux_provider",
    "app.providers.gpt_image_provider",
    "app.providers.gemini_script_provider",
    "app.providers.claude_script_provider",
    "app.providers.openai_script_provider",
    "app.providers.deepseek_script_provider",
    # Sprint217 - SNS 계정 연동(Epic 61). 라우터가 함수 안에서 들이므로
    # 여기에 적어 둔다. PyInstaller가 함수 안의 import도 따라가기는
    # 하지만, 이것들이 빠지면 [로그인]이 ImportError로 죽고 그 화면은
    # 정확히 예전의 "눌러도 아무 반응 없음"이 된다 - 짐작에 맡기지 않는다.
    "app.services.social_accounts",
    "app.services.credential_paths",
    "app.services.secret_box",
    "app.providers.upload.oauth_loopback",
    "app.providers.upload.tiktok_oauth_service",
    "app.providers.upload.google_oauth_service",
    "app.providers.upload.instagram_oauth_service",
    # google_auth_oauthlib가 loopback 흐름에서 늦게 들이는 것들.
    "google_auth_oauthlib.flow",
    "googleapiclient.discovery",
]

a = Analysis(
    [os.path.join(REPO, "launcher.py")],
    pathex=[REPO],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 묶을 때만 쓰는 것들. 넣으면 크기만 커진다.
    excludes=["pytest", "PyInstaller", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Sprint171 - 안에 든 ffmpeg를 뺀다.
#
# imageio_ffmpeg에는 PyInstaller가 스스로 붙이는 훅이 있어서, 우리가
# binaries에 아무것도 적지 않아도 제 ffmpeg(87MB)를 함께 넣는다.
# Sprint170은 "안에 넣지 않고 옆에 둔다"고 했는데 실제로는 양쪽에 있었고,
# 그 결과 tools/ffmpeg.exe를 지워도 프로그램은 아무 말도 하지 않았다 -
# 없는 것을 없다고 말하기로 한 약속이 조용히 깨져 있었다(Sprint171 실측).
#
# 모듈 자체는 뺄 수 없다 - moviepy가 들인다. 딸려 온 실행 파일만 뺀다.
a.binaries = TOC([
    entry for entry in a.binaries
    if "imageio_ffmpeg" not in os.path.normpath(entry[0]).split(os.sep)
])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=app_info.NAME,
    version=version_resource.write(STAGING),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 창을 띄운다. 주소와 내 것이 어디 있는지, 무엇이 없는지를
    # 그 창이 말한다 - 숨기면 안 될 때 아무 말도 없다.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
