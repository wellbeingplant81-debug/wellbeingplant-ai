"""
Sprint150 - 내 PC의 자료를 목록으로 만든다 (Epic 57, Phase 1).

돈이 들지 않는 제작을 하려면 그림과 소리를 어디선가 가져와야 하고,
가장 싼 곳은 이미 가지고 있는 폴더다.

무엇을 적는가
-------------
파일에서 읽을 수 있는 것만 적는다.

    path      어디 있는가
    kind      images / videos / music / voice - 폴더 이름이 정한다
    name      파일 이름
    tags      파일 이름과 폴더 이름에서 끊어 낸 낱말
    size      바이트
    modified  마지막으로 바뀐 때
    width     그림일 때만. PIL이 읽어 준다
    height

내용을 들여다보지 않는다
------------------------
그림 안에 무엇이 찍혔는지는 모른다. 그것을 알려면 모델을 불러야 하고,
그러면 돈이 들지 않는다는 말이 거짓이 된다.

그래서 tags는 파일 이름에서 온다 - "무릎_스트레칭_01.png"이면
["무릎", "스트레칭", "01"]이다. 사람이 이름을 잘 지어 두면 잘 찾히고,
아니면 잘 안 찾힌다. 그 사실을 숨기지 않는다.

폴더 이름이 종류를 정한다
-------------------------
    <root>/images/...   그림
    <root>/videos/...   영상
    <root>/music/...    배경음악
    <root>/voice/...    목소리

그 넷 밖의 폴더는 세지 않는다 - 무엇으로 쓸지 알 수 없기 때문이다.
"""

import json
import os
import re

INDEX_FILENAME = "local_library.json"

IMAGES = "images"
VIDEOS = "videos"
MUSIC = "music"
VOICE = "voice"

KINDS = (IMAGES, VIDEOS, MUSIC, VOICE)

EXTENSIONS = {
    IMAGES: (".png", ".jpg", ".jpeg", ".webp", ".bmp"),
    VIDEOS: (".mp4", ".mov", ".mkv", ".webm", ".avi"),
    MUSIC: (".mp3", ".wav", ".m4a", ".flac", ".ogg"),
    VOICE: (".wav", ".mp3", ".m4a", ".flac", ".ogg"),
}

# 낱말을 끊는 자리. 사람이 파일 이름에 쓰는 것들이다.
_SPLIT = re.compile(r"[\s_\-.,()\[\]]+")

VERSION = 1


def _tags(path: str, root: str, kind: str) -> list:
    """
    파일 이름과 그 위 폴더 이름에서 낱말을 끊어 낸다.

    내용을 보지 않는다 - 이름이 곧 우리가 아는 전부다.
    """

    relative = os.path.relpath(path, os.path.join(root, kind))
    stem = os.path.splitext(relative)[0]

    words = [w.strip().lower() for w in _SPLIT.split(stem.replace(os.sep, " "))]

    seen, tags = set(), []

    for word in words:
        if not word or word in seen:
            continue
        seen.add(word)
        tags.append(word)

    return tags


def _size_of(path: str):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _modified_of(path: str):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _dimensions(path: str):
    """그림의 크기. 읽지 못하면 None - 추측하지 않는다."""

    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def scan(root: str) -> dict:
    """
    폴더를 훑어 목록을 만든다. 파일은 한 바이트도 건드리지 않는다.

    없는 폴더는 없는 대로 둔다 - 그림만 모아 둔 사람도 있다.
    """

    items = []

    for kind in KINDS:
        folder = os.path.join(root, kind)

        if not os.path.isdir(folder):
            continue

        for base, _, names in os.walk(folder):
            for name in sorted(names):
                if not name.lower().endswith(EXTENSIONS[kind]):
                    continue

                path = os.path.join(base, name)

                item = {
                    "path": path,
                    "kind": kind,
                    "name": name,
                    "tags": _tags(path, root, kind),
                    "size": _size_of(path),
                    "modified": _modified_of(path),
                }

                if kind == IMAGES:
                    width, height = _dimensions(path)
                    item["width"] = width
                    item["height"] = height

                items.append(item)

    return {"version": VERSION, "root": root, "items": items}


def save(project_path: str, index: dict) -> str:
    """만든 목록을 프로젝트 옆에 적는다."""

    from app.utils.atomic_write import atomic_write_json

    path = os.path.join(project_path, INDEX_FILENAME)
    atomic_write_json(path, index)

    return path


def load(project_path: str) -> dict:
    """적어 둔 목록. 없으면 빈 것 - 훑은 적이 없다는 뜻이다."""

    try:
        with open(os.path.join(project_path, INDEX_FILENAME),
                  encoding="utf-8") as f:
            found = json.load(f)
    except Exception:
        return {"version": VERSION, "root": None, "items": []}

    if not isinstance(found, dict):
        return {"version": VERSION, "root": None, "items": []}

    found.setdefault("items", [])

    return found


def counts(index: dict) -> dict:
    """종류마다 몇 개인가. 화면이 그대로 보여 준다."""

    found = {kind: 0 for kind in KINDS}

    for item in index.get("items") or []:
        if item.get("kind") in found:
            found[item["kind"]] += 1

    return found


def search(index: dict, words, kind: str = IMAGES) -> list:
    """
    낱말이 많이 겹치는 것부터 돌려준다. 하나도 안 겹치면 빈 목록이다.

    억지로 아무거나 고르지 않는다 - 안 맞는 그림을 넣느니 없다고
    말하는 편이 낫다.
    """

    wanted = [w.strip().lower() for w in (words or []) if w and w.strip()]

    if not wanted:
        return []

    scored = []

    for item in index.get("items") or []:
        if item.get("kind") != kind:
            continue

        tags = set(item.get("tags") or [])
        hits = sum(1 for word in wanted if word in tags)

        if hits:
            scored.append((hits, item))

    scored.sort(key=lambda pair: (-pair[0], pair[1]["path"]))

    return [item for _, item in scored]
