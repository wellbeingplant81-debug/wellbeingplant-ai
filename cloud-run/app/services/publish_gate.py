"""
Sprint147 - 올리기 전에 사람이 고치고, 올리기 전에 한 번 본다
(Epic 56, Phase 24).

Render가 끝나면 publish_package.json이 놓인다. 지금까지 화면은 그것을
읽기만 했다 - 제목이 마음에 들지 않아도 고칠 자리가 없었다.

무엇을 고칠 수 있는가
---------------------
    title · description · tags

이 셋뿐이다. 나머지는 만들어진 것이거나(category_id, duration) 다른
자리가 정한 것이라(privacy_status, playlist_title) 화면이 손댈 일이
아니다. 영상도 scene도 여기서 건드리지 않는다.

만들지 않는다
-------------
여기는 메타데이터를 만드는 자리가 아니다. 이미 놓인 것을 읽어 사람이
고친 세 칸만 바꿔 다시 적는다 - 나머지 칸은 그대로 둔다. 없는 파일을
새로 만들지도 않는다.

현재 엔진을 고른 채로 고치면
----------------------------
다시 렌더할 때 metadata_service가 그 자리를 다시 만든다(current는
"엔진이 만든다"는 뜻이다). 그러면 사람이 고친 글이 사라진다.

숨기지 않고 화면이 그 사실을 말한다. 유지하려면 metadata_provider를
manual로 두면 된다 - manual은 "사람이 직접 쓴다"는 뜻이라 엔진이
만들지 않고 놓인 것을 그대로 쓴다(Sprint129).
"""

import os

PACKAGE_FILENAME = "publish_package.json"

FINAL_VIDEO = os.path.join("video", "final_short.mp4")

THUMBNAIL = os.path.join("thumbnail", "thumbnail.png")

# 사람이 고칠 수 있는 칸. 나머지는 만들어진 것이다.
EDITABLE = ("title", "description", "tags")


def _path(project_path: str) -> str:
    return os.path.join(project_path, PACKAGE_FILENAME)


def package(project_path: str):
    """놓여 있는 것을 그대로 읽는다. 없으면 None - 만들지 않는다."""

    from app.services import studio_service

    found = studio_service._load(_path(project_path))

    return found if isinstance(found, dict) else None


def save_edits(project_path: str, edits: dict) -> dict:
    """
    사람이 고친 세 칸만 바꿔 다시 적는다.

    없는 파일을 만들지 않는다 - 만들 재료가 없는데 빈 껍데기를 남기면
    업로드가 그것을 진짜 메타데이터로 읽는다(metadata_service가 같은
    이유로 그렇게 한다).
    """

    from app.utils.atomic_write import atomic_write_json

    current = package(project_path)

    if current is None:
        raise ValueError(
            "아직 publish_package.json이 없습니다. 영상을 먼저 만드십시오."
        )

    changed = dict(current)

    for key in EDITABLE:
        if key in (edits or {}):
            changed[key] = edits[key]

    atomic_write_json(_path(project_path), changed)

    return changed


def problems(project_path: str) -> list:
    """
    지금 올리면 무엇이 걸리는가. 고쳐 주지 않고 말만 한다.

    올린 뒤에 알면 늦는다 - 되돌릴 수 없는 자리이기 때문이다.
    """

    found = []

    if not os.path.exists(os.path.join(project_path, FINAL_VIDEO)):
        found.append("영상이 없습니다")

    data = package(project_path)

    if data is None:
        found.append("메타데이터가 없습니다")
        return found

    if not (data.get("title") or "").strip():
        found.append("제목을 입력해주세요")

    if not (data.get("description") or "").strip():
        found.append("설명을 입력해주세요")

    return found


def ready(project_path: str) -> bool:
    return not problems(project_path)
