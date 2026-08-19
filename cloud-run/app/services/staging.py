"""
Sprint222 - 대본보다 먼저 온 자료가 기다리는 자리 (Epic 64).

왜 이것이 생겼는가
------------------
지금 이미지 업로드는 이렇게 한다.

    staging = tempfile.mkdtemp()          <- 임시 자리를 만들고
    ...파일을 쓰고...
    provider.accept_manual(given, ...)    <- provider 에게 경로 목록을 주고
    shutil.rmtree(staging)                <- 버린다

그런데 accept_manual 은 scenes 를 요구한다. scenes 는 대본에서 나온다.
그래서 대본이 없으면 파일을 **받는 것 자체가** 막혔다 - 사람이 자료를
먼저 준비하는 것이 자연스러운데도 그럴 수 없었다.

이 파일이 하는 일은 하나뿐이다. **그 임시 자리를 영구 자리로 바꾼다.**
대본이 생기면 같은 경로 목록을 같은 accept_manual 에 넘긴다.

그래서 여기에는 매칭 규칙이 없다
--------------------------------
어떤 파일이 몇 번 scene 으로 가는지는 여전히 provider 가 정한다.
이 파일은 "무엇을 받았는지" 만 기억한다. 매칭을 여기에 한 줄이라도
적으면, 그날부터 규칙이 두 곳에 살게 된다.

원본 이름을 바꾸지 않는다
-------------------------
incoming_files.sort_key 가 **basename 의 숫자**로 순서를 정한다.
이름을 image_001.png 로 바꾸면 그 순서가 통째로 달라지고, 사람이
0001/0002 로 적어 둔 뜻이 사라진다.

그래서 이름은 그대로 두고, 대신 자산마다 제 폴더를 준다.

    .staging/images/<asset_id>/무릎 스트레칭.png

basename 은 원본 그대로이므로 sort_key 가 보는 것이 달라지지 않는다.
같은 이름을 두 번 넣어도 서로 덮지 않는다.

어떤 종류를 받는가
------------------
**이미지와 음성뿐이다.** 사람이 준 파일을 프로젝트에 놓는 provider 가
그 둘뿐이기 때문이다(image_import · voice_import).

    음악  전역이다 - %APPDATA%\\AI영상제작소\\music\\inbox 에 산다.
          프로젝트의 것이 아니므로 여기 두면 두 곳에 살게 된다.
    영상  들어오는 길이 없다. 영상은 산출물이지 입력이 아니다.

없는 길을 화면에 그리지 않는다 - 받아 놓고 쓰지 못하면 그것이 가장
나쁜 거짓말이다.
"""

import os
import shutil
import uuid
from datetime import datetime

from app.utils.atomic_write import atomic_write_json

DIRNAME = ".staging"
MANIFEST = "manifest.json"

IMAGE = "image"
VOICE = "voice"

# 종류 -> (폴더 이름, 그 종류를 놓는 provider 이름)
KINDS = {
    IMAGE: ("images", "image_import"),
    VOICE: ("voice", "voice_import"),
}


class StagingError(ValueError):
    """받을 수 없는 것을 받으려 했다."""


def root(project_path: str) -> str:
    return os.path.join(project_path, DIRNAME)


def manifest_path(project_path: str) -> str:
    return os.path.join(root(project_path), MANIFEST)


def kind_root(project_path: str, kind: str) -> str:
    if kind not in KINDS:
        raise StagingError(
            f"받을 수 없는 종류입니다: {kind!r} "
            f"(받는 것: {', '.join(sorted(KINDS))})")

    return os.path.join(root(project_path), KINDS[kind][0])


def provider_name(kind: str) -> str:
    return KINDS[kind][1]


def _read(project_path: str) -> dict:
    """
    manifest 를 읽는다. 없거나 깨졌으면 빈 것으로 본다.

    깨진 manifest 때문에 프로그램이 안 켜지면 안 된다 - 여기 있는 것은
    사람이 넣어 둔 파일의 목록일 뿐이고, 파일 자체는 디스크에 있다.
    """

    import json

    try:
        with open(manifest_path(project_path), encoding="utf-8") as f:
            found = json.load(f)
    except (OSError, ValueError):
        return {"version": 1, "assets": []}

    if not isinstance(found, dict) or not isinstance(found.get("assets"), list):
        return {"version": 1, "assets": []}

    return found


def _write(project_path: str, data: dict) -> None:
    os.makedirs(root(project_path), exist_ok=True)
    atomic_write_json(manifest_path(project_path), data)


def _safe_name(name: str) -> str:
    """
    파일 이름만 남긴다. 경로가 섞여 있으면 이름만 뽑는다.

    라우터가 이미 basename 을 하지만 여기서도 한다 - 이 함수를 부르는
    자리가 라우터 하나라는 보장이 없고, 이것이 뚫리면 프로젝트 밖에
    쓰게 된다.
    """

    only = os.path.basename(str(name or "").replace("\\", "/"))

    if not only or only in (".", ".."):
        raise StagingError("파일 이름이 없습니다.")

    return only


def add(project_path: str, kind: str, uploads) -> list:
    """
    받은 것을 자리에 놓는다. 놓은 자산들을 돌려준다.

    uploads 는 (이름, 읽을 수 있는 것) 의 목록이다. UploadFile 을
    그대로 받지 않는다 - 이 서비스가 FastAPI 를 알 이유가 없다.
    """

    where = kind_root(project_path, kind)

    data = _read(project_path)
    added = []

    for name, stream in uploads:
        only = _safe_name(name)
        asset_id = uuid.uuid4().hex[:12]

        holder = os.path.join(where, asset_id)
        os.makedirs(holder, exist_ok=True)

        target = os.path.join(holder, only)

        with open(target, "wb") as f:
            shutil.copyfileobj(stream, f)

        asset = {
            "asset_id": asset_id,
            "kind": kind,
            "name": only,
            "size": os.path.getsize(target),
            "added_at": datetime.now().isoformat(timespec="seconds"),
        }

        data["assets"].append(asset)
        added.append(asset)

    _write(project_path, data)

    return added


def listing(project_path: str) -> dict:
    """
    무엇이 담겼는가. 디스크에 없는 것은 빼고 말한다.

    manifest 와 실제 파일이 어긋날 수 있다 - 사람이 탐색기로 지웠을
    수도 있다. 그때 화면이 "이미지 12개"라고 말하면 apply 에서야
    들통난다. 셀 때 실제로 있는지 본다.
    """

    data = _read(project_path)

    alive = []

    for asset in data["assets"]:
        if os.path.exists(_path_of(project_path, asset)):
            alive.append(asset)

    counts = {kind: 0 for kind in KINDS}

    for asset in alive:
        if asset.get("kind") in counts:
            counts[asset["kind"]] += 1

    return {"assets": alive, "counts": counts, "total": len(alive)}


def _path_of(project_path: str, asset: dict) -> str:
    try:
        where = kind_root(project_path, asset.get("kind"))
    except StagingError:
        return ""

    return os.path.join(where, str(asset.get("asset_id", "")),
                        str(asset.get("name", "")))


def paths_for(project_path: str, kind: str) -> list:
    """
    provider 에게 넘길 경로 목록. **넣은 순서 그대로.**

    정렬하지 않는다 - 순서를 정하는 것은 provider 안의 _collect 이고,
    그것이 incoming_files.sort_key 를 쓴다. 여기서 미리 정렬하면
    규칙이 두 곳에 살게 된다.
    """

    found = []

    for asset in listing(project_path)["assets"]:
        if asset.get("kind") != kind:
            continue

        where = _path_of(project_path, asset)

        if where:
            found.append(where)

    return found


def remove(project_path: str, asset_id: str) -> bool:
    """하나 뺀다. 없던 것이면 False."""

    data = _read(project_path)

    keep = []
    dropped = None

    for asset in data["assets"]:
        if asset.get("asset_id") == asset_id and dropped is None:
            dropped = asset
        else:
            keep.append(asset)

    if dropped is None:
        return False

    where = _path_of(project_path, dropped)

    if where:
        shutil.rmtree(os.path.dirname(where), ignore_errors=True)

    data["assets"] = keep
    _write(project_path, data)

    return True


def clear(project_path: str, kind: str) -> int:
    """
    한 종류를 통째로 비운다. 뺀 개수를 돌려준다.

    apply 가 끝난 뒤에 부르라고 만든 것이 **아니다.** apply 는 원본을
    복사만 하고(image_import._place: "원본은 손대지 않는다"), 사람이
    다시 연결하고 싶을 수 있다. 지우는 것은 사람이 정한다.
    """

    data = _read(project_path)

    keep = []
    gone = 0

    for asset in data["assets"]:
        if asset.get("kind") == kind:
            where = _path_of(project_path, asset)

            if where:
                shutil.rmtree(os.path.dirname(where), ignore_errors=True)

            gone += 1
        else:
            keep.append(asset)

    data["assets"] = keep
    _write(project_path, data)

    return gone
